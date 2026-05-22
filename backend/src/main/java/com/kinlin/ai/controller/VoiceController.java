package com.kinlin.ai.controller;

import com.kinlin.ai.dto.ChatResponse;
import com.kinlin.ai.dto.TtsRequest;
import com.kinlin.ai.security.AuthenticatedUser;
import com.kinlin.ai.service.VoiceService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.UUID;

/**
 * 语音控制器
 */
@RestController
@RequestMapping("/voice")
@RequiredArgsConstructor
public class VoiceController {

    private final VoiceService voiceService;

    /**
     * 发送语音消息
     */
    @PostMapping("/chat")
    public ResponseEntity<ChatResponse> sendVoiceMessage(
            @RequestParam("audio") MultipartFile audioFile,
            @RequestParam(value = "roleId", required = false) UUID roleId,
            @RequestParam(value = "contextId", required = false) String contextId,
            @RequestHeader(value = "X-User-Id", required = false) UUID userId
    ) {
        try {
            userId = AuthenticatedUser.currentUserId().orElse(userId);
            byte[] audioData = audioFile.getBytes();
            ChatResponse response = voiceService.processVoiceMessage(
                    audioData, roleId, contextId, userId
            );
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }

    /**
     * 文本转语音
     */
    @PostMapping("/tts")
    public ResponseEntity<byte[]> textToSpeech(@RequestBody TtsRequest request) {
        // 参数验证和限制
        double finalSpeed = request.getSpeed() != null ? 
                Math.max(0.5, Math.min(2.0, request.getSpeed())) : 1.0;
        double finalPitch = request.getPitch() != null ? 
                Math.max(0.5, Math.min(2.0, request.getPitch())) : 1.0;
        
        byte[] audioData = voiceService.textToSpeech(
                request.getText(),
                request.getVoice() != null ? request.getVoice() : "default",
                finalSpeed,
                finalPitch
        );
        
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_OCTET_STREAM);
        headers.setContentDispositionFormData("attachment", "speech.wav");
        
        return ResponseEntity.ok()
                .headers(headers)
                .body(audioData);
    }
}

