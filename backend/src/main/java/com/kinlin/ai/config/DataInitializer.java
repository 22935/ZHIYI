package com.kinlin.ai.config;

import com.kinlin.ai.entity.Role;
import com.kinlin.ai.repository.RoleRepository;
import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import java.util.HashMap;
import java.util.Map;

/**
 * 数据初始化器
 * 初始化内置角色数据
 */
@Slf4j
@Component
@Profile("!test")
@RequiredArgsConstructor
public class DataInitializer {

    private final RoleRepository roleRepository;

    @PostConstruct
    public void initBuiltinRoles() {
        if (roleRepository.findByRoleType(Role.RoleType.BUILTIN).isEmpty()) {
            log.info("初始化内置角色数据...");
            
            // 律师角色
            createRole("律师", "专业的法律顾问，擅长解答法律问题",
                    "你是一位经验丰富的律师，擅长解答法律问题，提供专业的法律建议。你的回答应该严谨、专业、逻辑清晰。",
                    0.9, 0.5, 0.8, "严谨、专业、逻辑清晰");
            
            // 教师角色
            createRole("教师", "耐心的教育工作者，擅长知识讲解",
                    "你是一位优秀的教师，擅长知识讲解和辅导学习。你的回答应该耐心、细致、循循善诱。",
                    0.6, 0.9, 0.7, "耐心、细致、循循善诱");
            
            // 程序员角色
            createRole("程序员", "技术专家，擅长解决编程问题",
                    "你是一位资深的程序员，擅长代码问题排查和提供编程建议。你的回答应该简洁、技术导向、注重实践。",
                    0.5, 0.6, 0.95, "简洁、技术导向、注重实践");
            
            // 作家角色
            createRole("作家", "创意写作者，擅长文字创作",
                    "你是一位才华横溢的作家，擅长创意写作和文章润色。你的回答应该富有创意、文采斐然。",
                    0.7, 0.8, 0.6, "富有创意、文采斐然");
            
            log.info("内置角色数据初始化完成");
        }
    }

    private void createRole(String name, String description, String systemPrompt,
                           double formality, double warmth, double technicalLevel,
                           String personality) {
        Role role = new Role();
        role.setName(name);
        role.setDescription(description);
        role.setRoleType(Role.RoleType.BUILTIN);
        role.setSystemPrompt(systemPrompt);
        
        // 设置对话风格
        Map<String, Object> dialogueStyle = new HashMap<>();
        dialogueStyle.put("formality", formality);
        dialogueStyle.put("warmth", warmth);
        dialogueStyle.put("technical_level", technicalLevel);
        role.setDialogueStyle(dialogueStyle);
        
        // 设置性格特点
        Map<String, Object> personalityMap = new HashMap<>();
        String[] traits = personality.split("、");
        for (String trait : traits) {
            personalityMap.put(trait, true);
        }
        role.setPersonality(personalityMap);
        
        // 设置头像配置
        Map<String, Object> avatarConfig = new HashMap<>();
        avatarConfig.put("style", name.equals("律师") ? "professional" : 
                        name.equals("教师") ? "friendly" :
                        name.equals("程序员") ? "casual" : "artistic");
        role.setAvatarConfig(avatarConfig);
        
        roleRepository.save(role);
    }
}

