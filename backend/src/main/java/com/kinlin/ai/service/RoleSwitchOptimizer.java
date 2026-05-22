package com.kinlin.ai.service;

import com.kinlin.ai.entity.Role;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.Map;

/**
 * 角色切换性能优化服务
 * 通过缓存和预加载优化角色切换性能
 */
@Slf4j
@Service
public class RoleSwitchOptimizer {

    private final RoleService roleService;
    
    // 角色配置缓存
    private final Map<UUID, Role> roleCache = new ConcurrentHashMap<>();
    
    // 角色上下文缓存（预加载）
    private final Map<UUID, Map<String, Object>> roleContextCache = new ConcurrentHashMap<>();
    
    public RoleSwitchOptimizer(RoleService roleService) {
        this.roleService = roleService;
    }
    
    /**
     * 获取角色（带缓存）
     */
    @Cacheable(value = "roles", key = "#roleId")
    public Role getRoleCached(UUID roleId) {
        // 先从内存缓存获取
        Role cached = roleCache.get(roleId);
        if (cached != null) {
            log.debug("从内存缓存获取角色: {}", roleId);
            return cached;
        }
        
        // 从数据库获取
        Role role = roleService.getRole(roleId)
                .orElseThrow(() -> new RuntimeException("角色不存在: " + roleId));
        
        // 存入缓存
        roleCache.put(roleId, role);
        
        // 预加载角色上下文
        preloadRoleContext(roleId);
        
        log.debug("从数据库加载角色并缓存: {}", roleId);
        return role;
    }
    
    /**
     * 预加载角色上下文
     */
    private void preloadRoleContext(UUID roleId) {
        if (roleContextCache.containsKey(roleId)) {
            return; // 已经预加载
        }
        
        try {
            Role role = roleCache.get(roleId);
            if (role == null) {
                role = roleService.getRole(roleId).orElse(null);
                if (role == null) return;
                roleCache.put(roleId, role);
            }
            
            // 构建角色上下文
            Map<String, Object> context = buildRoleContext(role);
            roleContextCache.put(roleId, context);
            
            log.debug("预加载角色上下文: {}", roleId);
        } catch (Exception e) {
            log.warn("预加载角色上下文失败: {}", roleId, e);
        }
    }
    
    /**
     * 构建角色上下文
     */
    private Map<String, Object> buildRoleContext(Role role) {
        Map<String, Object> context = new HashMap<>();
        
        context.put("role_id", role.getId().toString());
        context.put("name", role.getName());
        context.put("description", role.getDescription());
        context.put("personality", role.getPersonality());
        context.put("system_prompt", role.getSystemPrompt());
        context.put("dialogue_style", role.getDialogueStyle());
        
        return context;
    }
    
    /**
     * 获取角色上下文（快速访问）
     */
    public Map<String, Object> getRoleContext(UUID roleId) {
        // 先从缓存获取
        Map<String, Object> context = roleContextCache.get(roleId);
        if (context != null) {
            return context;
        }
        
        // 如果缓存中没有，获取角色并构建上下文
        Role role = getRoleCached(roleId);
        context = buildRoleContext(role);
        roleContextCache.put(roleId, context);
        
        return context;
    }
    
    /**
     * 预热常用角色
     */
    public void warmupCommonRoles() {
        log.info("开始预热常用角色...");
        
        try {
            // 获取所有内置角色
            var builtinRoles = roleService.getBuiltinRoles();
            
            for (Role role : builtinRoles) {
                try {
                    getRoleCached(role.getId());
                    log.debug("预热角色: {}", role.getName());
                } catch (Exception e) {
                    log.warn("预热角色失败: {}", role.getId(), e);
                }
            }
            
            log.info("常用角色预热完成，共预热 {} 个角色", builtinRoles.size());
        } catch (Exception e) {
            log.error("预热常用角色失败", e);
        }
    }
    
    /**
     * 清除角色缓存
     */
    public void clearRoleCache(UUID roleId) {
        roleCache.remove(roleId);
        roleContextCache.remove(roleId);
        log.debug("清除角色缓存: {}", roleId);
    }
    
    /**
     * 清除所有缓存
     */
    public void clearAllCache() {
        roleCache.clear();
        roleContextCache.clear();
        log.info("清除所有角色缓存");
    }
    
    /**
     * 获取缓存统计
     */
    public Map<String, Object> getCacheStats() {
        Map<String, Object> stats = new ConcurrentHashMap<>();
        stats.put("role_cache_size", roleCache.size());
        stats.put("context_cache_size", roleContextCache.size());
        return stats;
    }
}





