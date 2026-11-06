package com.kinlin.ai.integration;

import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationVersion;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * J1.4A §八/§九：真实 PostgreSQL 迁移权威测试。
 *
 * <p>证明链（任务书 §八）：</p>
 * <pre>empty PostgreSQL database → Flyway → V1→latest → migration SUCCESS
 *   → Hibernate ddl-auto=validate SUCCESS → JPA ApplicationContext 启动</pre>
 *
 * <p>测试使用项目真实 {@code classpath:db/migration/**}，Spring 上下文启动本身
 * 就是 "Flyway migrate + Hibernate validate" 双关卡：任何一处失败上下文都无法起来。
 * 迁移数量不硬编码，而是与 classpath 当前 migration 集做集合比对（§九）。</p>
 */
@SpringBootTest
class PostgresMigrationIntegrationTest extends PostgresIntegrationTestBase {

    private static final Pattern VERSION_PATTERN = Pattern.compile("V(\\d+(?:_\\d+)*)__");

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private Flyway flyway;

    @Test
    void applicationContextBootsOnPostgresWithFlywayMigrateAndHibernateValidate() {
        // 上下文已带 Flyway(enabled=true, 真实 db/migration) 与 Hibernate ddl-auto=validate
        // 两个启动关卡在真实 PostgreSQL 上全部通过，这里落一个显式断言。
        assertThat(flyway).isNotNull();
        Integer tableCount = jdbcTemplate.queryForObject(
                "select count(*) from information_schema.tables "
                        + "where table_schema = 'public' and table_name in "
                        + "('users','roles','conversations','messages')",
                Integer.class);
        assertThat(tableCount).isEqualTo(4);
    }

    @Test
    void flywaySchemaHistoryExistsWithEveryMigrationSuccessful() {
        Integer historyRows = jdbcTemplate.queryForObject(
                "select count(*) from flyway_schema_history where version is not null",
                Integer.class);
        assertThat(historyRows).isNotNull();
        assertThat(historyRows).isGreaterThan(0);

        Boolean allSuccess = jdbcTemplate.queryForObject(
                "select bool_and(success) from flyway_schema_history where version is not null",
                Boolean.class);
        assertThat(allSuccess).as("flyway_schema_history 全部 success=true").isTrue();
    }

    @Test
    void appliedMigrationSetMatchesCurrentClasspathMigrationSet() {
        List<String> applied = jdbcTemplate.queryForList(
                "select version from flyway_schema_history where version is not null",
                String.class);
        List<String> classpath = classpathMigrationVersions();

        assertThat(classpath).as("classpath db/migration 必须非空").isNotEmpty();
        assertThat(applied).containsExactlyInAnyOrderElementsOf(classpath);
        // latest applied == classpath 最新版本（按数值序，不硬编码总数）
        assertThat(MigrationVersion.fromVersion(lastOf(applied)))
                .isEqualTo(MigrationVersion.fromVersion(lastOf(classpath)));
    }

    /**
     * §二十二.3：迁移可重复性——在第二个全新空数据库上重放
     * V1→latest 并通过 Flyway 自身的 validate。fresh 语义保留：同一自管临时
     * 实例上的另一个全新 database，从空 schema 开始，不共享第一库的任何对象。
     */
    @Test
    void migrationReplaysCleanlyOnAFreshEmptyDatabase() {
        String freshUrl = POSTGRES.createDatabase("kinlin_fresh");

        Flyway migrate = Flyway.configure()
                .dataSource(freshUrl, POSTGRES.getUsername(), POSTGRES.getPassword())
                .load();
        int executed = migrate.migrate().migrationsExecuted;
        List<String> classpath = classpathMigrationVersions();
        assertThat(executed).isEqualTo(classpath.size());

        Flyway.configure()
                .dataSource(freshUrl, POSTGRES.getUsername(), POSTGRES.getPassword())
                .load()
                .validate();
    }

    private static String lastOf(List<String> versions) {
        return versions.stream()
                .max(Comparator.comparing(MigrationVersion::fromVersion))
                .orElseThrow();
    }

    /** 扫描 classpath 当前真实 migration 集（db/migration/V*.sql），不硬编码数量。 */
    static List<String> classpathMigrationVersions() {
        try {
            Resource[] resources = new PathMatchingResourcePatternResolver()
                    .getResources("classpath*:db/migration/V*.sql");
            return Arrays.stream(resources)
                    .map(resource -> {
                        Matcher matcher = VERSION_PATTERN.matcher(resource.getFilename());
                        if (!matcher.find()) {
                            throw new IllegalStateException(
                                    "无法从 migration 文件名解析版本: " + resource.getFilename());
                        }
                        return matcher.group(1);
                    })
                    .toList();
        } catch (Exception e) {
            throw new IllegalStateException("扫描 classpath db/migration 失败", e);
        }
    }
}
