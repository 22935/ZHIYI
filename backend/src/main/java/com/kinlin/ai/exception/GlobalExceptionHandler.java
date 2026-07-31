package com.kinlin.ai.exception;

import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingRequestHeaderException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.support.MissingServletRequestPartException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import java.util.HashMap;
import java.util.Map;
import com.kinlin.ai.observability.TraceContext;

/**
 * 全局异常处理器
 */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<Map<String, Object>> handleMaxUploadSize(MaxUploadSizeExceededException ex) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE).body(Map.of(
                "success", false,
                "error", "MATERIAL_TOO_LARGE",
                "message", "文件不能超过 10MB"
        ));
    }

    @ExceptionHandler(MissingServletRequestPartException.class)
    public ResponseEntity<Map<String, Object>> handleMissingMultipartPart(MissingServletRequestPartException ex) {
        return ResponseEntity.unprocessableEntity().body(Map.of(
                "success", false,
                "error", "MATERIAL_FILE_REQUIRED",
                "message", "上传请求缺少 file 字段"
        ));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handleValidationExceptions(
            MethodArgumentNotValidException ex) {
        Map<String, String> errors = new HashMap<>();
        ex.getBindingResult().getAllErrors().forEach((error) -> {
            String fieldName = ((FieldError) error).getField();
            String errorMessage = error.getDefaultMessage();
            errors.put(fieldName, errorMessage);
        });
        
        Map<String, Object> response = new HashMap<>();
        response.put("success", false);
        response.put("message", "参数验证失败");
        response.put("errors", errors);
        
        return ResponseEntity.badRequest().body(response);
    }

    @ExceptionHandler(com.kinlin.ai.exception.BusinessException.class)
    public ResponseEntity<Map<String, Object>> handleBusinessException(
            com.kinlin.ai.exception.BusinessException ex) {
        Map<String, Object> response = new HashMap<>();
        response.put("success", false);
        response.put("code", ex.getCode());
        response.put("message", ex.getMessage());
        
        return ResponseEntity.badRequest().body(response);
    }

    @ExceptionHandler(com.kinlin.ai.exception.ResourceNotFoundException.class)
    public ResponseEntity<Map<String, Object>> handleResourceNotFoundException(
            com.kinlin.ai.exception.ResourceNotFoundException ex) {
        Map<String, Object> response = new HashMap<>();
        response.put("success", false);
        response.put("code", ex.getCode());
        response.put("message", ex.getMessage());
        
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(response);
    }

    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<Map<String, Object>> handleNoResourceFoundException(NoResourceFoundException ex) {
        log.warn("资源未找到: {}", ex.getResourcePath());
        
        Map<String, Object> response = new HashMap<>();
        response.put("success", false);
        response.put("message", "请求的接口不存在: " + ex.getResourcePath());
        response.put("error", "请检查请求路径是否正确");
        
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(response);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, Object>> handleHttpMessageNotReadableException(
            HttpMessageNotReadableException ex) {
        log.warn("JSON解析错误: {}", ex.getMessage());
        
        Map<String, Object> response = new HashMap<>();
        response.put("success", false);
        response.put("message", "请求参数格式错误");
        
        // 提取更友好的错误信息
        String errorMessage = ex.getMessage();
        if (errorMessage != null && errorMessage.contains("Unrecognized field")) {
            response.put("error", "请求中包含未知字段，请检查请求参数");
        } else if (errorMessage != null && errorMessage.contains("JSON parse error")) {
            response.put("error", "JSON格式错误，请检查请求体格式");
        } else {
            response.put("error", errorMessage);
        }
        
        return ResponseEntity.badRequest().body(response);
    }

    @ExceptionHandler(MissingRequestHeaderException.class)
    public ResponseEntity<Map<String, Object>> handleMissingRequestHeaderException(
            MissingRequestHeaderException ex) {
        Map<String, Object> response = new HashMap<>();
        response.put("success", false);
        response.put("message", "缺少必要请求头");
        response.put("error", ex.getHeaderName() + " 请求头缺失");

        // Authorization 缺失属于未认证场景，返回 401；其余头缺失返回 400。
        if ("Authorization".equalsIgnoreCase(ex.getHeaderName())) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(response);
        }
        return ResponseEntity.badRequest().body(response);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> handleGenericException(Exception ex) {
        log.error("Unexpected error", ex);
        
        Map<String, Object> response = new HashMap<>();
        response.put("success", false);
        response.put("message", "服务器内部错误");
        response.put("error", "INTERNAL_SERVER_ERROR");
        response.put("traceId", TraceContext.currentTraceId());
        
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(response);
    }
}

