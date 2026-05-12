import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const DEV_PROXY_TIMEOUT_MS = 240000
const BACKEND_PROXY_TARGET = process.env.DEV_BACKEND_PROXY_TARGET || 'http://localhost:5000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 3000,
    strictPort: false,
    proxy: {
      '/api': {
        target: BACKEND_PROXY_TARGET,
        changeOrigin: true,
        timeout: DEV_PROXY_TIMEOUT_MS,
        proxyTimeout: DEV_PROXY_TIMEOUT_MS,
        // 智能处理：部分控制器有/api前缀，部分没有
        // 对于有/api前缀的控制器（如digital-human），保留前缀
        // 对于没有/api前缀的控制器（如auth、chat），去掉前缀
        rewrite: (path) => {
          // 这些路径已经有/api前缀，保留
          const keepApiPrefix = [
            '/api/digital-human',
            '/api/kylin-os',
            '/api/emotion',
            '/api/knowledge-graph',
            '/api/role-fusion',
            '/api/alerts',
            '/api/feedback',
            '/api/federated-models'
          ]

          // 检查是否需要保留/api前缀
          if (keepApiPrefix.some(prefix => path.startsWith(prefix))) {
            return path // 保留/api前缀
          }

          // 其他路径去掉/api前缀
          return path.replace(/^\/api/, '')
        },
        configure: (proxy, _options) => {
          proxy.on('error', (err, _req, _res) => {
            console.log('proxy error', err);
          });
          proxy.on('proxyReq', (proxyReq, req, _res) => {
            console.log('Sending Request to the Target:', req.method, req.url); 
          });
          proxy.on('proxyRes', (proxyRes, req, _res) => {
            console.log('Received Response from the Target:', proxyRes.statusCode, req.url);
          });
        }
      },
      // 代理 /ai 路径到Python服务（通过Java后端）
      '/ai': {
        target: BACKEND_PROXY_TARGET,
        changeOrigin: true,
        timeout: DEV_PROXY_TIMEOUT_MS,
        proxyTimeout: DEV_PROXY_TIMEOUT_MS,
        rewrite: (path) => {
          // /ai 路径需要转发到Java后端，Java后端会代理到Python服务
          // 所以保持路径不变，Java后端会处理
          return path
        },
        configure: (proxy, _options) => {
          proxy.on('error', (err, _req, _res) => {
            console.log('AI proxy error', err);
          });
          proxy.on('proxyReq', (proxyReq, req, _res) => {
            console.log('Sending AI Request to the Target:', req.method, req.url);
          });
          proxy.on('proxyRes', (proxyRes, req, _res) => {
            console.log('Received AI Response from the Target:', proxyRes.statusCode, req.url);
          });
        }
      }
    }
  }
})
