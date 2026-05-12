"""
加密服务
提供差分隐私、对称加密、同态加密等功能
使用专业加密库（如果可用）
"""
import logging
import numpy as np
from typing import Dict, Any, Optional
import hashlib
import base64

logger = logging.getLogger(__name__)

# 尝试导入专业加密库
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import padding
    CRYPTOGRAPHY_AVAILABLE = True
    logger.info("cryptography已安装，使用专业加密")
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    logger.warning("cryptography未安装，使用简化加密。安装: pip install cryptography")

# 尝试导入差分隐私库
try:
    import diffprivlib
    DIFFPRIVLIB_AVAILABLE = True
    logger.info("diffprivlib已安装，使用专业差分隐私")
except ImportError:
    DIFFPRIVLIB_AVAILABLE = False
    logger.warning("diffprivlib未安装，使用简化差分隐私。安装: pip install diffprivlib")


class EncryptionService:
    """加密服务"""
    
    def __init__(self):
        """初始化加密服务"""
        self.use_cryptography = CRYPTOGRAPHY_AVAILABLE
        self.use_diffprivlib = DIFFPRIVLIB_AVAILABLE
        
        # 生成或加载密钥（实际应用中应该安全存储）
        self._symmetric_key = self._generate_key()
    
    def _generate_key(self) -> bytes:
        """生成对称加密密钥"""
        # 实际应用中应该使用安全的密钥管理
        key_material = b"federal_hub_federated_learning_key_2025"
        return hashlib.sha256(key_material).digest()
    
    def add_differential_privacy(
        self,
        parameters: Dict[str, Any],
        epsilon: float = 1.0,
        delta: float = 1e-5
    ) -> Dict[str, Any]:
        """
        添加差分隐私噪声（增强实现）
        
        Args:
            parameters: 模型参数
            epsilon: 隐私预算（越小越隐私，但噪声越大）
            delta: 失败概率（通常很小，如1e-5）
        
        Returns:
            添加噪声后的参数
        """
        try:
            if self.use_diffprivlib:
                return self._add_dp_with_diffprivlib(parameters, epsilon, delta)
            else:
                return self._add_dp_simplified(parameters, epsilon)
        except Exception as e:
            logger.warning(f"差分隐私添加失败: {e}，使用简化实现")
            return self._add_dp_simplified(parameters, epsilon)
    
    def _add_dp_with_diffprivlib(
        self,
        parameters: Dict[str, Any],
        epsilon: float,
        delta: float
    ) -> Dict[str, Any]:
        """使用diffprivlib进行专业差分隐私"""
        try:
            from diffprivlib.mechanisms import GaussianMechanism
            
            noisy_parameters = {}
            for key, value in parameters.items():
                if isinstance(value, list):
                    value_array = np.array(value)
                    
                    # 计算敏感度（L2范数的上界）
                    sensitivity = np.linalg.norm(value_array)
                    
                    # 创建高斯机制
                    mechanism = GaussianMechanism(
                        epsilon=epsilon,
                        delta=delta,
                        sensitivity=sensitivity
                    )
                    
                    # 添加噪声
                    noisy_value = mechanism.randomise(value_array)
                    noisy_parameters[key] = noisy_value.tolist()
                else:
                    noisy_parameters[key] = value
            
            logger.info(f"差分隐私噪声已添加（epsilon={epsilon}, delta={delta}）")
            return noisy_parameters
        except Exception as e:
            logger.warning(f"使用diffprivlib失败: {e}，降级到简化实现")
            return self._add_dp_simplified(parameters, epsilon)
    
    def _add_dp_simplified(
        self,
        parameters: Dict[str, Any],
        epsilon: float
    ) -> Dict[str, Any]:
        """简化差分隐私实现（降级方案）"""
        # 使用拉普拉斯机制（简化版）
        # 敏感度假设为1.0
        sensitivity = 1.0
        scale = sensitivity / epsilon
        
        noisy_parameters = {}
        for key, value in parameters.items():
            if isinstance(value, list):
                value_array = np.array(value)
                # 添加拉普拉斯噪声
                noise = np.random.laplace(0, scale, size=value_array.shape)
                noisy_parameters[key] = (value_array + noise).tolist()
            else:
                noisy_parameters[key] = value
        
        logger.info(f"差分隐私噪声已添加（简化实现，epsilon={epsilon}）")
        return noisy_parameters
    
    def encrypt_symmetric(
        self,
        data: bytes,
        key: Optional[bytes] = None
    ) -> bytes:
        """
        对称加密（AES）
        
        Args:
            data: 要加密的数据
            key: 加密密钥（可选，默认使用内部密钥）
        
        Returns:
            加密后的数据（base64编码）
        """
        if not self.use_cryptography:
            logger.warning("cryptography未安装，使用简化加密")
            return self._encrypt_simplified(data)
        
        try:
            if key is None:
                key = self._symmetric_key
            
            # 使用AES-256-CBC
            iv = np.random.bytes(16)  # 初始化向量
            
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()
            
            # 填充数据
            padder = padding.PKCS7(128).padder()
            padded_data = padder.update(data) + padder.finalize()
            
            # 加密
            encrypted = encryptor.update(padded_data) + encryptor.finalize()
            
            # 将IV和加密数据组合，然后base64编码
            combined = iv + encrypted
            encoded = base64.b64encode(combined)
            
            logger.debug("对称加密成功（AES-256-CBC）")
            return encoded
        except Exception as e:
            logger.error(f"对称加密失败: {e}", exc_info=True)
            return self._encrypt_simplified(data)
    
    def decrypt_symmetric(
        self,
        encrypted_data: bytes,
        key: Optional[bytes] = None
    ) -> bytes:
        """
        对称解密（AES）
        
        Args:
            encrypted_data: 加密的数据（base64编码）
            key: 解密密钥（可选）
        
        Returns:
            解密后的数据
        """
        if not self.use_cryptography:
            logger.warning("cryptography未安装，使用简化解密")
            return self._decrypt_simplified(encrypted_data)
        
        try:
            if key is None:
                key = self._symmetric_key
            
            # Base64解码
            combined = base64.b64decode(encrypted_data)
            
            # 提取IV和加密数据
            iv = combined[:16]
            encrypted = combined[16:]
            
            # 解密
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            padded_data = decryptor.update(encrypted) + decryptor.finalize()
            
            # 去除填充
            unpadder = padding.PKCS7(128).unpadder()
            data = unpadder.update(padded_data) + unpadder.finalize()
            
            logger.debug("对称解密成功（AES-256-CBC）")
            return data
        except Exception as e:
            logger.error(f"对称解密失败: {e}", exc_info=True)
            return self._decrypt_simplified(encrypted_data)
    
    def _encrypt_simplified(self, data: bytes) -> bytes:
        """简化加密（降级方案）"""
        # 简单的XOR加密（仅用于演示，不推荐生产环境）
        key_bytes = self._symmetric_key
        encrypted = bytearray()
        for i, byte in enumerate(data):
            encrypted.append(byte ^ key_bytes[i % len(key_bytes)])
        return base64.b64encode(bytes(encrypted))
    
    def _decrypt_simplified(self, encrypted_data: bytes) -> bytes:
        """简化解密（降级方案）"""
        try:
            decoded = base64.b64decode(encrypted_data)
            key_bytes = self._symmetric_key
            decrypted = bytearray()
            for i, byte in enumerate(decoded):
                decrypted.append(byte ^ key_bytes[i % len(key_bytes)])
            return bytes(decrypted)
        except Exception as e:
            logger.error(f"简化解密失败: {e}")
            return encrypted_data
    
    def encrypt_parameters(
        self,
        parameters: Dict[str, Any],
        method: str = "symmetric"
    ) -> Dict[str, Any]:
        """
        加密模型参数
        
        Args:
            parameters: 模型参数字典
            method: 加密方法（symmetric/homomorphic）
        
        Returns:
            加密后的参数
        """
        if method == "symmetric":
            # 对称加密：将参数序列化为JSON，然后加密
            try:
                import json
                json_data = json.dumps(parameters).encode('utf-8')
                encrypted_data = self.encrypt_symmetric(json_data)
                return {
                    "encrypted": encrypted_data.decode('utf-8'),
                    "method": "symmetric",
                    "format": "json"
                }
            except Exception as e:
                logger.error(f"参数加密失败: {e}", exc_info=True)
                return parameters
        else:
            # 同态加密（简化实现，实际应该使用专业库如TenSEAL）
            logger.warning("同态加密使用简化实现，生产环境应使用专业库（如TenSEAL）")
            # 同态加密需要特殊的库支持，这里提供框架
            return {
                "encrypted": parameters,  # 简化：直接返回
                "method": "homomorphic_simplified",
                "note": "需要集成TenSEAL等专业同态加密库"
            }
    
    def decrypt_parameters(
        self,
        encrypted_parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        解密模型参数
        
        Args:
            encrypted_parameters: 加密的参数
        
        Returns:
            解密后的参数
        """
        method = encrypted_parameters.get("method", "symmetric")
        
        if method == "symmetric":
            try:
                import json
                encrypted_data = encrypted_parameters.get("encrypted", "").encode('utf-8')
                decrypted_data = self.decrypt_symmetric(encrypted_data)
                parameters = json.loads(decrypted_data.decode('utf-8'))
                return parameters
            except Exception as e:
                logger.error(f"参数解密失败: {e}", exc_info=True)
                return encrypted_parameters
        else:
            # 同态加密解密（简化实现）
            return encrypted_parameters.get("encrypted", {})


# 全局加密服务实例
encryption_service = EncryptionService()

