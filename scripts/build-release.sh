#!/bin/bash

# 联邦智枢 发布包构建脚本
# 用于构建可部署的发布包，包含所有必要的文件和配置

set -e

PROJECT_DIR=$(cd "$(dirname "$0")/.." && pwd)
VERSION=${1:-"latest"}
RELEASE_DIR="$PROJECT_DIR/release/kinlin-ai-$VERSION"
BUILD_DATE=$(date +%Y%m%d_%H%M%S)

echo "=========================================="
echo "联邦智枢 发布包构建脚本"
echo "版本: $VERSION"
echo "构建时间: $BUILD_DATE"
echo "=========================================="

# 创建发布目录
echo "创建发布目录..."
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"/{docker,config,scripts,docs}

# 1. 复制Docker配置文件
echo "复制Docker配置..."
cp -r docker/* "$RELEASE_DIR/docker/"
cp docker-compose.prod.yml "$RELEASE_DIR/docker/" 2>/dev/null || true

# 2. 构建Docker镜像并导出
echo "构建Docker镜像..."
cd "$PROJECT_DIR"

# 构建后端镜像
echo "构建后端镜像..."
cd backend
docker build -t kinlin-ai-backend:$VERSION .
docker save kinlin-ai-backend:$VERSION -o "$RELEASE_DIR/docker/kinlin-ai-backend-$VERSION.tar"

# 构建AI服务镜像
echo "构建AI服务镜像..."
cd ../agent
docker build -t kinlin-ai-service:$VERSION .
docker save kinlin-ai-service:$VERSION -o "$RELEASE_DIR/docker/kinlin-ai-service-$VERSION.tar"

# 构建前端镜像
echo "构建前端镜像..."
cd ../frontend
docker build -t kinlin-ai-frontend:$VERSION .
docker save kinlin-ai-frontend:$VERSION -o "$RELEASE_DIR/docker/kinlin-ai-frontend-$VERSION.tar"

cd "$PROJECT_DIR"

# 3. 创建配置模板
echo "创建配置模板..."
cat > "$RELEASE_DIR/config/.env.template" << 'EOF'
# 数据库配置
DB_USERNAME=kinlin_ai
DB_PASSWORD=请修改为强密码
REDIS_PASSWORD=请修改为强密码

# 麒麟AI API配置
KYLIN_AI_API_KEY=请填写您的麒麟AI API密钥
KYLIN_AI_ENDPOINT=https://api.kylin.ai

# 应用配置
SPRING_PROFILES_ACTIVE=prod
ENVIRONMENT=production
LOG_LEVEL=INFO

# JWT配置（可选，使用默认值）
APP_JWT_SECRET=请修改为至少64字符的随机字符串
EOF

# 4. 创建快速部署脚本
echo "创建部署脚本..."
cat > "$RELEASE_DIR/install.sh" << 'SCRIPT_EOF'
#!/bin/bash

# 联邦智枢 一键安装脚本

set -e

INSTALL_DIR="/opt/kinlin_ai"
VERSION="__VERSION__"

echo "=========================================="
echo "联邦智枢 安装程序"
echo "版本: $VERSION"
echo "=========================================="

# 检查是否为root
if [ "$EUID" -ne 0 ]; then 
    echo "请使用sudo运行此脚本"
    exit 1
fi

# 1. 安装Docker
if ! command -v docker &> /dev/null; then
    echo "安装Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    systemctl start docker
    systemctl enable docker
fi

# 2. 加载Docker镜像
echo "加载Docker镜像..."
cd "$(dirname "$0")/docker"
docker load -i kinlin-ai-backend-__VERSION__.tar
docker load -i kinlin-ai-service-__VERSION__.tar
docker load -i kinlin-ai-frontend-__VERSION__.tar

# 3. 配置环境变量
echo "配置环境变量..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    mkdir -p "$INSTALL_DIR"
    cp ../config/.env.template "$INSTALL_DIR/.env"
    echo ""
    echo "=========================================="
    echo "请编辑配置文件: $INSTALL_DIR/.env"
    echo "必须修改以下内容:"
    echo "  - DB_PASSWORD: 数据库密码"
    echo "  - REDIS_PASSWORD: Redis密码"
    echo "  - KYLIN_AI_API_KEY: 麒麟AI API密钥"
    echo "=========================================="
    read -p "配置完成后按Enter继续..."
fi

# 4. 启动服务
echo "启动服务..."
cd "$INSTALL_DIR"
cp -r "$(dirname "$0")/docker" .
cd docker
docker-compose -f docker-compose.prod.yml up -d

echo ""
echo "=========================================="
echo "安装完成！"
echo "=========================================="
echo "访问地址: http://$(hostname -I | awk '{print $1}')"
echo ""
SCRIPT_EOF

# 替换版本号
sed -i "s/__VERSION__/$VERSION/g" "$RELEASE_DIR/install.sh"
chmod +x "$RELEASE_DIR/install.sh"

# 5. 创建卸载脚本
cat > "$RELEASE_DIR/uninstall.sh" << 'EOF'
#!/bin/bash

echo "卸载联邦智枢..."

cd /opt/kinlin_ai/docker 2>/dev/null || exit 0
docker-compose -f docker-compose.prod.yml down -v

echo "卸载完成"
EOF
chmod +x "$RELEASE_DIR/uninstall.sh"

# 6. 复制文档
echo "复制文档..."
cp docs/麒麟操作系统部署指南.md "$RELEASE_DIR/docs/" 2>/dev/null || true
cp README.md "$RELEASE_DIR/docs/README.md" 2>/dev/null || true

# 7. 创建README
cat > "$RELEASE_DIR/README.md" << EOF
# 联邦智枢 发布包

版本: $VERSION
构建时间: $BUILD_DATE

## 快速安装

1. 解压发布包
2. 运行安装脚本: \`sudo ./install.sh\`
3. 编辑配置文件: \`/opt/kinlin_ai/.env\`
4. 重新运行安装脚本完成部署

## 文件说明

- \`docker/\`: Docker镜像文件
- \`config/\`: 配置文件模板
- \`install.sh\`: 一键安装脚本
- \`uninstall.sh\`: 卸载脚本
- \`docs/\`: 文档

## 详细说明

请查看 \`docs/麒麟操作系统部署指南.md\`
EOF

# 8. 创建压缩包
echo "创建发布包..."
cd "$PROJECT_DIR/release"
tar -czf "kinlin-ai-$VERSION-$BUILD_DATE.tar.gz" "kinlin-ai-$VERSION"

echo ""
echo "=========================================="
echo "构建完成！"
echo "=========================================="
echo "发布包位置: $PROJECT_DIR/release/kinlin-ai-$VERSION-$BUILD_DATE.tar.gz"
echo "发布目录: $RELEASE_DIR"
echo ""

