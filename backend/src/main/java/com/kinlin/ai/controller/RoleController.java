package com.kinlin.ai.controller;

import com.kinlin.ai.dto.RoleCreateRequest;
import com.kinlin.ai.entity.Role;
import com.kinlin.ai.security.AuthenticatedUser;
import com.kinlin.ai.service.RoleService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

/**
 * 角色控制器
 */
@RestController
@RequestMapping("/roles")
@RequiredArgsConstructor
public class RoleController {

    private final RoleService roleService;
    private final com.kinlin.ai.service.RoleSwitchOptimizer roleSwitchOptimizer;

    /**
     * 获取内置角色列表
     */
    @GetMapping("/builtin")
    public ResponseEntity<List<Role>> getBuiltinRoles() {
        List<Role> roles = roleService.getBuiltinRoles();
        return ResponseEntity.ok(roles);
    }

    /**
     * 获取自定义角色列表
     */
    @GetMapping("/custom")
    public ResponseEntity<List<Role>> getCustomRoles(
            @RequestHeader(value = "X-User-Id", required = false) UUID userId
    ) {
        userId = resolveUserId(userId);
        List<Role> roles = roleService.getCustomRoles(userId);
        return ResponseEntity.ok(roles);
    }

    /**
     * 获取角色详情（使用缓存优化）
     */
    @GetMapping("/{roleId}")
    public ResponseEntity<Role> getRole(@PathVariable UUID roleId) {
        try {
            Role role = roleSwitchOptimizer.getRoleCached(roleId);
            return ResponseEntity.ok(role);
        } catch (RuntimeException e) {
            return ResponseEntity.notFound().build();
        }
    }
    
    /**
     * 获取角色上下文（快速访问）
     */
    @GetMapping("/{roleId}/context")
    public ResponseEntity<java.util.Map<String, Object>> getRoleContext(@PathVariable UUID roleId) {
        try {
            java.util.Map<String, Object> context = roleSwitchOptimizer.getRoleContext(roleId);
            return ResponseEntity.ok(context);
        } catch (RuntimeException e) {
            return ResponseEntity.notFound().build();
        }
    }
    
    /**
     * 获取缓存统计
     */
    @GetMapping("/cache/stats")
    public ResponseEntity<java.util.Map<String, Object>> getCacheStats() {
        return ResponseEntity.ok(roleSwitchOptimizer.getCacheStats());
    }
    
    /**
     * 清除角色缓存
     */
    @DeleteMapping("/cache/{roleId}")
    public ResponseEntity<Void> clearRoleCache(@PathVariable UUID roleId) {
        roleSwitchOptimizer.clearRoleCache(roleId);
        return ResponseEntity.ok().build();
    }

    /**
     * 创建自定义角色
     */
    @PostMapping("/custom")
    public ResponseEntity<Role> createRole(
            @Valid @RequestBody RoleCreateRequest request,
            @RequestHeader(value = "X-User-Id", required = false) UUID userId
    ) {
        userId = resolveUserId(userId);
        Role role = roleService.createRole(request, userId);
        return ResponseEntity.status(HttpStatus.CREATED).body(role);
    }

    /**
     * 更新角色
     */
    @PutMapping("/{roleId}")
    public ResponseEntity<Role> updateRole(
            @PathVariable UUID roleId,
            @Valid @RequestBody RoleCreateRequest request,
            @RequestHeader(value = "X-User-Id", required = false) UUID userId
    ) {
        userId = resolveUserId(userId);
        return roleService.updateRole(roleId, request, userId)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    /**
     * 删除角色
     */
    @DeleteMapping("/{roleId}")
    public ResponseEntity<Void> deleteRole(
            @PathVariable UUID roleId,
            @RequestHeader(value = "X-User-Id", required = false) UUID userId
    ) {
        userId = resolveUserId(userId);
        if (roleService.deleteRole(roleId, userId)) {
            return ResponseEntity.ok().build();
        }
        return ResponseEntity.notFound().build();
    }

    private UUID resolveUserId(UUID userIdHeader) {
        return AuthenticatedUser.currentUserId().orElse(userIdHeader);
    }
}
