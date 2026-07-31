package com.kinlin.ai.mapper;

import com.kinlin.ai.dto.RoleCreateRequest;
import com.kinlin.ai.dto.RoleResponse;
import com.kinlin.ai.entity.Role;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.factory.Mappers;

/**
 * 角色映射器
 * 用于Entity和DTO之间的转换
 */
@Mapper(componentModel = "spring")
public interface RoleMapper {

    RoleMapper INSTANCE = Mappers.getMapper(RoleMapper.class);

    @Mapping(target = "roleType", expression = "java(role.getRoleType().name())")
    RoleResponse toResponse(Role role);

    @Mapping(target = "id", ignore = true)
    @Mapping(target = "createdAt", ignore = true)
    @Mapping(target = "updatedAt", ignore = true)
    @Mapping(target = "roleType", ignore = true)
    @Mapping(target = "userId", ignore = true)
    @Mapping(target = "stableKey", ignore = true)
    Role toEntity(RoleCreateRequest request);
}

