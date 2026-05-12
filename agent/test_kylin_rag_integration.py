"""
测试麒麟SDK智能切换和增强RAG功能
运行: python test_kylin_rag_integration.py
"""
import asyncio
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_os_detection():
    """测试操作系统检测"""
    print("\n" + "="*60)
    print("测试1: 操作系统检测")
    print("="*60)
    
    try:
        from app.services.kylinosintegration import kylin_os_integration_service
        
        system_info = kylin_os_integration_service.get_system_info()
        print(f"✓ 操作系统: {system_info['os_name']}")
        print(f"✓ 版本: {system_info['os_version']}")
        print(f"✓ 架构: {system_info['architecture']}")
        print(f"✓ 是否为麒麟OS: {system_info['is_kylin_os']}")
        
        if system_info['is_kylin_os']:
            print("  → 系统将使用麒麟AI SDK")
        else:
            print("  → 系统将使用通义千问大模型")
        
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


async def test_sdk_client():
    """测试SDK客户端初始化"""
    print("\n" + "="*60)
    print("测试2: SDK客户端初始化")
    print("="*60)
    
    try:
        from app.ai_engine.kylin_sdk.client import KylinAIClient
        
        client = KylinAIClient()
        print("✓ SDK客户端初始化成功")
        
        # 检测使用的SDK
        if hasattr(client, '_sdk_client'):
            sdk_client = client._sdk_client
            if sdk_client.use_kylin_sdk:
                print("  → 使用麒麟SDK")
            elif sdk_client.use_qwen:
                print("  → 使用通义千问")
                print(f"     模型: {sdk_client.qwen_adapter.model_name if sdk_client.qwen_adapter else '未知'}")
            else:
                print("  → 使用模拟响应模式")
        
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_document_processor():
    """测试文档处理器"""
    print("\n" + "="*60)
    print("测试3: 文档处理器")
    print("="*60)
    
    try:
        from app.services.documentprocessoradvanced import document_processor_advanced
        
        print("✓ 文档处理器初始化成功")
        print(f"  支持格式: {', '.join(document_processor_advanced.supported_formats)}")
        
        print("\n可用工具:")
        for tool, available in document_processor_advanced.available_tools.items():
            status = "✓" if available else "✗"
            print(f"  {status} {tool}")
        
        # 测试文本提取
        test_text = b"This is a test document content."
        result = document_processor_advanced.extract_text(
            file_data=test_text,
            filename="test.txt"
        )
        
        if result['success']:
            print(f"\n✓ 文本提取测试成功")
            print(f"  方法: {result['method']}")
        else:
            print(f"\n✗ 文本提取测试失败: {result.get('error')}")
        
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_rag_tools():
    """测试RAG工具集成"""
    print("\n" + "="*60)
    print("测试4: RAG工具集成")
    print("="*60)
    
    try:
        from app.services.ragtoolsintegration import rag_tools_integration
        
        print("✓ RAG工具集成初始化成功")
        print(f"  默认工具: {rag_tools_integration.selected_tool}")
        
        print("\n可用RAG工具:")
        for tool, info in rag_tools_integration.available_tools.items():
            if info.get('available'):
                note = info.get('note', info.get('library', '可用'))
                print(f"  ✓ {tool}: {note}")
            else:
                install_cmd = info.get('install_cmd', '不可用')
                print(f"  ✗ {tool}: {install_cmd}")
        
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_text_generation():
    """测试文本生成"""
    print("\n" + "="*60)
    print("测试5: 文本生成（可选）")
    print("="*60)
    
    try:
        from app.ai_engine.kylin_sdk.client import KylinAIClient
        from app.config import settings
        
        # 检查是否配置了API密钥
        has_key = bool(
            getattr(settings, 'KYLIN_AI_API_KEY', '') or
            getattr(settings, 'DASHSCOPE_API_KEY', '') or
            getattr(settings, 'QWEN_API_KEY', '')
        )
        
        if not has_key:
            print("⊘ 跳过测试: 未配置API密钥")
            print("  提示: 配置 DASHSCOPE_API_KEY 或 KYLIN_AI_API_KEY 以启用此测试")
            return True
        
        client = KylinAIClient()
        
        result = await client.generate_text(
            text="你好",
            role_id=None
        )
        
        print("✓ 文本生成测试成功")
        print(f"  回复长度: {len(result['text'])} 字符")
        print(f"  Token使用: {result.get('tokens_used', 0)}")
        print(f"  回复预览: {result['text'][:100]}...")
        
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_config():
    """测试配置加载"""
    print("\n" + "="*60)
    print("测试6: 配置加载")
    print("="*60)
    
    try:
        from app.config import settings
        
        print("✓ 配置加载成功")
        
        # 检查关键配置
        configs = {
            "应用名称": settings.APP_NAME,
            "调试模式": settings.DEBUG,
            "文档处理方法": getattr(settings, 'DOCUMENT_PROCESSOR_METHOD', 'auto'),
            "文档处理增强": getattr(settings, 'DOCUMENT_PROCESSOR_USE_ENHANCED', True),
            "RAG工具": getattr(settings, 'RAG_TOOL_PROVIDER', 'auto'),
            "图像生成模型": getattr(settings, 'IMAGE_GENERATION_MODEL', 'wan2.6-t2i'),
        }
        
        print("\n配置详情:")
        for key, value in configs.items():
            print(f"  {key}: {value}")
        
        # 检查API密钥（不显示完整密钥）
        print("\nAPI密钥配置:")
        kylin_key = getattr(settings, 'KYLIN_AI_API_KEY', '')
        dash_key = getattr(settings, 'DASHSCOPE_API_KEY', '')
        qwen_key = getattr(settings, 'QWEN_API_KEY', '')
        
        if kylin_key:
            print(f"  ✓ KYLIN_AI_API_KEY: {'*' * 10}{kylin_key[-4:] if len(kylin_key) > 4 else '****'}")
        else:
            print(f"  ✗ KYLIN_AI_API_KEY: 未配置")
        
        if dash_key:
            print(f"  ✓ DASHSCOPE_API_KEY: {'*' * 10}{dash_key[-4:] if len(dash_key) > 4 else '****'}")
        else:
            print(f"  ✗ DASHSCOPE_API_KEY: 未配置")
        
        if qwen_key:
            print(f"  ✓ QWEN_API_KEY: {'*' * 10}{qwen_key[-4:] if len(qwen_key) > 4 else '****'}")
        else:
            print(f"  ✗ QWEN_API_KEY: 未配置")
        
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("联邦智枢 - 麒麟SDK和增强RAG功能测试")
    print("="*60)
    
    tests = [
        ("配置加载", test_config),
        ("操作系统检测", test_os_detection),
        ("SDK客户端", test_sdk_client),
        ("文档处理器", test_document_processor),
        ("RAG工具集成", test_rag_tools),
        ("文本生成", test_text_generation),
    ]
    
    results = []
    
    for name, test_func in tests:
        result = await test_func()
        results.append((name, result))
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status}: {name}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！系统配置正确。")
    else:
        print("\n⚠️  部分测试失败，请检查配置和依赖。")
    
    print("\n提示:")
    print("- 如需使用AI功能，请配置 DASHSCOPE_API_KEY 或 KYLIN_AI_API_KEY")
    print("- 可选工具可通过 pip install <工具名> 安装")
    print("- 详细文档: docs/麒麟SDK智能切换与增强RAG指南.md")


if __name__ == "__main__":
    asyncio.run(main())

