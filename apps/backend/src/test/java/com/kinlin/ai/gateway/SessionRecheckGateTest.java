package com.kinlin.ai.gateway;

import com.kinlin.ai.service.LoginSessionService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.codec.ServerSentEvent;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * INT-2F-4B：会话复核交付门单元合同（真实时钟短参数，不依赖虚拟时钟）。
 *
 * <p>覆盖：租期放行与刷新、撤销信号、查询失败/超时 fail-closed、
 * 单在途护栏、迟到结果不得复活、空闲（无 admit）也终止。</p>
 */
class SessionRecheckGateTest {

    private final LoginSessionService loginSessionService = mock(LoginSessionService.class);
    private final UUID sid = UUID.randomUUID();
    private final UUID userId = UUID.randomUUID();

    private SessionRecheckGate gate;

    @AfterEach
    void tearDown() {
        if (gate != null) {
            gate.close();
        }
    }

    private SessionRecheckGate gate(long periodMs, long timeoutMs, long leaseMs) {
        gate = new SessionRecheckGate(loginSessionService, sid, userId,
                Duration.ofMillis(periodMs), Duration.ofMillis(timeoutMs), Duration.ofMillis(leaseMs),
                Schedulers.boundedElastic(), () -> { });
        return gate;
    }

    private static ServerSentEvent<String> event(String data) {
        return ServerSentEvent.<String>builder(data).build();
    }

    @Test
    void activeSessionRenewsLeaseAndEventsKeepFlowing() {
        when(loginSessionService.isSessionActive(sid, userId)).thenReturn(true);
        SessionRecheckGate gate = gate(60, 400, 250);
        gate.start(Schedulers.parallel());

        // 初租期立即放行；跨多个复核周期（租期 250ms < 400ms 观测窗）仍持续放行
        for (int i = 0; i < 8; i++) {
            final String payload = "e" + i;
            StepVerifier.create(gate.admit(event(payload)))
                    .expectNextMatches(e -> payload.equals(e.data()))
                    .verifyComplete();
            sleepQuietly(60);
        }
        assertThat(gate.isRevoked()).isFalse();
    }

    @Test
    void revokedSessionEmitsSignalAndAdmitFailsClosed() {
        when(loginSessionService.isSessionActive(sid, userId)).thenReturn(false);
        SessionRecheckGate gate = gate(50, 400, 250);
        gate.start(Schedulers.parallel());

        // 周期任务不依赖 admit：空闲也必须发出终止信号（P+查询 ≤ ~450ms）
        StepVerifier.create(gate.revocationSignal())
                .expectComplete()
                .verify(Duration.ofMillis(1500));
        assertThat(gate.isRevoked()).isTrue();

        StepVerifier.create(gate.admit(event("late")))
                .expectError(SessionRecheckGate.SessionRevokedException.class)
                .verify(Duration.ofSeconds(1));
    }

    @Test
    void queryFailureFailsClosedImmediately() {
        when(loginSessionService.isSessionActive(any(), any()))
                .thenThrow(new org.springframework.dao.DataAccessResourceFailureException("db down"));
        SessionRecheckGate gate = gate(50, 400, 250);
        gate.start(Schedulers.parallel());

        StepVerifier.create(gate.revocationSignal())
                .expectComplete()
                .verify(Duration.ofMillis(1500));
        assertThat(gate.isRevoked()).isTrue();
    }

    @Test
    void slowQueryTimesOutFailsClosedAndLateResultCannotRevive() {
        when(loginSessionService.isSessionActive(any(), any())).thenAnswer(invocation -> {
            Thread.sleep(600); // 超过 Q=200ms：订阅级超时先触发
            return true; // 迟到的"有效"结果必须无权复活
        });
        SessionRecheckGate gate = gate(50, 200, 250);
        gate.start(Schedulers.parallel());

        StepVerifier.create(gate.revocationSignal())
                .expectComplete()
                .verify(Duration.ofMillis(1200));
        assertThat(gate.isRevoked()).isTrue();

        // 迟到结果落定后仍保持终止
        sleepQuietly(700);
        assertThat(gate.isRevoked()).isTrue();
        StepVerifier.create(gate.admit(event("after-late")))
                .expectError(SessionRecheckGate.SessionRevokedException.class)
                .verify(Duration.ofSeconds(1));
    }

    @Test
    void singleInFlightQueryPerStream() {
        AtomicInteger calls = new AtomicInteger();
        when(loginSessionService.isSessionActive(any(), any())).thenAnswer(invocation -> {
            calls.incrementAndGet();
            Thread.sleep(300); // 慢查询跨多个 tick（P=50ms）
            return true;
        });
        SessionRecheckGate gate = gate(50, 5_000, 5_000);
        gate.start(Schedulers.parallel());

        // 250ms < 慢查 300ms：窗口内约 5 个 tick，但首查未决期间只发起 1 次
        sleepQuietly(250);
        assertThat(calls.get()).isEqualTo(1);
    }

    @Test
    void expiredLeaseWithoutFreshObservationRejectsDelivery() {
        // 不依赖周期刷新：初租期 120ms 过期后 admit 必须拒绝（fail-closed）
        when(loginSessionService.isSessionActive(any(), any())).thenReturn(true);
        SessionRecheckGate gate = gate(60_000, 400, 120);
        gate.start(Schedulers.parallel());
        // 立即关闭周期任务（在途首查结果因 closed 不再刷新租期），仅保留初租期语义
        gate.close();

        StepVerifier.create(gate.admit(event("in-lease")))
                .expectNextCount(1)
                .verifyComplete();
        sleepQuietly(200);
        StepVerifier.create(gate.admit(event("past-lease")))
                .expectError(SessionRecheckGate.SessionRevokedException.class)
                .verify(Duration.ofSeconds(1));
    }

    private static void sleepQuietly(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    @Test
    void leaseUsesElapsedTimeIncludingAcrossNanoTimeWraparound() {
        // A nanoTime origin is arbitrary and may be negative or wrap. Wall time
        // adjustments must have no role in this five-second validity interval.
        java.util.concurrent.atomic.AtomicLong time =
                new java.util.concurrent.atomic.AtomicLong(Long.MAX_VALUE - TimeUnit.SECONDS.toNanos(2));
        // The virtual clock must keep the periodic recheck dormant, but the
        // zero-delay first tick can still race ahead on loaded runners. An
        // unstubbed probe would default to false and fail-closed revoke before
        // the first admit; with this stub a racing tick only refreshes the lease
        // to the same t0+lease value and can never revoke.
        when(loginSessionService.isSessionActive(any(), any())).thenReturn(true);
        gate = new SessionRecheckGate(loginSessionService, sid, userId,
                Duration.ofSeconds(3), Duration.ofSeconds(1), Duration.ofSeconds(5),
                Schedulers.boundedElastic(), () -> { }, time::get);
        reactor.test.scheduler.VirtualTimeScheduler clock = reactor.test.scheduler.VirtualTimeScheduler.create();
        try {
            gate.start(clock);
            time.addAndGet(TimeUnit.SECONDS.toNanos(4));
            StepVerifier.create(gate.admit(event("within lease"))).expectNextCount(1).verifyComplete();
            time.addAndGet(TimeUnit.SECONDS.toNanos(1));
            StepVerifier.create(gate.admit(event("expired")))
                    .expectError(SessionRecheckGate.SessionRevokedException.class).verify();
        } finally {
            clock.dispose();
        }
    }
}
