#!/bin/bash
# Server Monitor 自动安装脚本 v2.3
# 支持密钥认证的性能监控 API
# 新增：配置管理入口

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 配置变量
SERVICE_NAME="server-monitor"
INSTALL_DIR="/usr/local/server-monitor"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
LISTEN_PORT=8627
SECRET_KEY=""

# 安装状态变量
IS_REINSTALL=false
EXISTING_CONFIG=""

# 打印函数
print_line() {
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
}

print_step() {
    echo -e "${GREEN}[√]${NC} ${1}"
}

print_info() {
    echo -e "${BLUE}[i]${NC} ${1}"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} ${1}"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} ${1}"
}

print_error() {
    echo -e "${RED}[✗]${NC} ${1}"
}

# 打印 Banner
print_banner() {
    clear
    echo -e "${GREEN}"
    cat << "EOF"
   ____                            __  __             _ _             
  / ___|  ___ _ ____   _____ _ __|  \/  | ___  _ __ (_) |_ ___  _ __ 
  \___ \ / _ \ '__\ \ / / _ \ '__| |\/| |/ _ \| '_ \| | __/ _ \| '__|
   ___) |  __/ |   \ V /  __/ |  | |  | | (_) | | | | | || (_) | |   
  |____/ \___|_|    \_/ \___|_|  |_|  |_|\___/|_| |_|_|\__\___/|_|   
                                                                      
         Performance Monitor API - Interactive Installer v2.3
EOF
    echo -e "${NC}"
    print_line
    echo ""
}

# 检查是否为 root 用户
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "此脚本需要 root 权限运行"
        echo "请使用: sudo \$0"
        exit 1
    fi
}

# 检查操作系统
check_os() {
    print_step "检查操作系统..."
    
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$NAME
        VER=$VERSION_ID
        print_success "操作系统: ${OS} ${VER}"
    else
        print_warning "无法确定操作系统版本"
    fi
}

# 检查 Python 3
check_python() {
    print_step "检查 Python 3 安装..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | awk '{print $2}')
        PYTHON_PATH=$(which python3)
        print_success "Python 3 已安装: ${PYTHON_VERSION}"
        print_info "Python 路径: ${PYTHON_PATH}"
    else
        print_error "Python 3 未安装"
        print_info "正在安装 Python 3..."
        
        if command -v apt-get &> /dev/null; then
            apt-get update -qq
            apt-get install -y python3 python3-pip
        elif command -v yum &> /dev/null; then
            yum install -y python3 python3-pip
        elif command -v dnf &> /dev/null; then
            dnf install -y python3 python3-pip
        else
            print_error "无法自动安装 Python 3，请手动安装后重试"
            exit 1
        fi
        
        print_success "Python 3 安装完成"
    fi
}

# 检查 systemd
check_systemd() {
    print_step "检查 systemd..."
    
    if command -v systemctl &> /dev/null; then
        print_success "systemd 可用"
    else
        print_error "systemd 不可用，无法创建服务"
        exit 1
    fi
}

# 生成随机密钥
generate_secret_key() {
    cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1
}

# 直接进入配置管理
enter_config_management() {
    if [[ ! -f "${INSTALL_DIR}/manage.sh" ]]; then
        print_error "配置管理脚本不存在"
        print_info "请先完成安装"
        echo ""
        read -p "按 Enter 键返回..." dummy
        return 1
    fi
    
    print_success "正在启动配置管理..."
    echo ""
    sleep 1
    exec bash ${INSTALL_DIR}/manage.sh
}

# 检测已安装的服务
check_existing_installation() {
    print_step "检查现有安装..."
    
    local has_service=false
    local has_directory=false
    local has_config=false
    
    # 检查 systemd 服务
    if [[ -f "$SERVICE_FILE" ]]; then
        has_service=true
        print_warning "检测到已安装的 systemd 服务"
    fi
    
    # 检查安装目录
    if [[ -d "$INSTALL_DIR" ]]; then
        has_directory=true
        print_warning "检测到已存在的安装目录: ${INSTALL_DIR}"
    fi
    
    # 检查配置文件
    if [[ -f "${INSTALL_DIR}/config.env" ]]; then
        has_config=true
        print_warning "检测到现有配置文件"
        EXISTING_CONFIG="${INSTALL_DIR}/config.env"
    fi
    
    # 如果检测到任何已安装组件
    if [[ "$has_service" == true ]] || [[ "$has_directory" == true ]]; then
        echo ""
        print_line
        echo -e "${YELLOW}检测到 Server Monitor 已安装！${NC}"
        print_line
        echo ""
        
        # 显示当前安装信息
        if [[ "$has_service" == true ]]; then
            if systemctl is-active --quiet ${SERVICE_NAME}; then
                echo -e "${GREEN}● 服务状态: 运行中${NC}"
            else
                echo -e "${RED}● 服务状态: 已停止${NC}"
            fi
            
            if systemctl is-enabled --quiet ${SERVICE_NAME} 2>/dev/null; then
                echo -e "${GREEN}● 开机自启: 已启用${NC}"
            fi
        fi
        
        if [[ "$has_config" == true ]]; then
            echo -e "${CYAN}● 配置文件: 存在${NC}"
            # 读取现有配置
            if [[ -f "$EXISTING_CONFIG" ]]; then
                local existing_port=$(grep "^LISTEN_PORT=" "$EXISTING_CONFIG" 2>/dev/null | cut -d'=' -f2)
                local existing_key=$(grep "^SECRET_KEY=" "$EXISTING_CONFIG" 2>/dev/null | cut -d'=' -f2)
                
                if [[ -n "$existing_port" ]]; then
                    echo -e "${CYAN}  - 监听端口: ${existing_port}${NC}"
                fi
                if [[ -n "$existing_key" ]]; then
                    echo -e "${CYAN}  - 访问密钥: ${existing_key:0:8}...${NC}"
                fi
            fi
        fi
        
        echo ""
        print_line
        echo -e "${CYAN}请选择操作:${NC}"
        echo "  1) 重新安装 (保留现有配置)"
        echo "  2) 全新安装 (删除所有配置)"
        echo "  3) 升级安装 (仅更新 Python 脚本)"
        echo "  4) 配置管理 (修改端口/密钥等)"
        echo "  5) 退出安装"
        print_line
        echo ""
        
        while true; do
            read -p "$(echo -e ${CYAN}"请输入选项 [1-5]: "${NC})" install_choice
            
            case $install_choice in
                1)
                    IS_REINSTALL=true
                    print_success "选择: 重新安装 (保留配置)"
                    echo ""
                    return 0
                    ;;
                2)
                    print_warning "选择: 全新安装 (将删除所有现有配置)"
                    read -p "$(echo -e ${YELLOW}"确认删除所有现有配置? [y/N]: "${NC})" confirm_clean
                    
                    if [[ "$confirm_clean" =~ ^[Yy]$ ]]; then
                        cleanup_existing_installation
                        print_success "已清理现有安装"
                        echo ""
                        return 0
                    else
                        print_info "已取消"
                        continue
                    fi
                    ;;
                3)
                    print_success "选择: 升级安装"
                    upgrade_installation
                    exit 0
                    ;;
                4)
                    print_success "选择: 配置管理"
                    enter_config_management
                    exit 0
                    ;;
                5)
                    print_info "退出安装"
                    exit 0
                    ;;
                *)
                    print_error "无效选项，请输入 1-5"
                    ;;
            esac
        done
    else
        print_success "未检测到现有安装，将执行全新安装"
    fi
    
    echo ""
}

# 清理现有安装
cleanup_existing_installation() {
    print_step "清理现有安装..."
    
    # 停止并禁用服务
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        print_info "停止服务..."
        systemctl stop ${SERVICE_NAME}
    fi
    
    if systemctl is-enabled --quiet ${SERVICE_NAME} 2>/dev/null; then
        print_info "禁用服务..."
        systemctl disable ${SERVICE_NAME}
    fi
    
    # 删除服务文件
    if [[ -f "$SERVICE_FILE" ]]; then
        print_info "删除服务文件..."
        rm -f "$SERVICE_FILE"
        systemctl daemon-reload
    fi
    
    # 删除安装目录
    if [[ -d "$INSTALL_DIR" ]]; then
        print_info "删除安装目录..."
        rm -rf "$INSTALL_DIR"
    fi
    
    print_success "清理完成"
}

# 仅升级 Python 脚本
upgrade_installation() {
    print_line
    echo -e "${CYAN}升级模式${NC}"
    print_line
    echo ""
    
    if [[ ! -d "$INSTALL_DIR" ]]; then
        print_error "安装目录不存在，无法升级"
        exit 1
    fi
    
    # 备份现有 server.py
    if [[ -f "${INSTALL_DIR}/server.py" ]]; then
        BACKUP_FILE="${INSTALL_DIR}/server.py.backup.$(date +%Y%m%d_%H%M%S)"
        cp "${INSTALL_DIR}/server.py" "$BACKUP_FILE"
        print_success "已备份现有脚本到: $BACKUP_FILE"
    fi
    
    # 创建优化版的 server.py
    print_step "更新 Python 脚本..."
    create_optimized_server_script
    
    # 重启服务
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        print_step "重启服务..."
        systemctl restart ${SERVICE_NAME}
        sleep 2
        
        if systemctl is-active --quiet ${SERVICE_NAME}; then
            print_success "服务重启成功"
        else
            print_error "服务重启失败"
            print_info "查看日志: journalctl -u ${SERVICE_NAME} -n 50"
        fi
    fi
    
    echo ""
    print_success "升级完成！"
    echo ""
}

# 创建优化版 server.py
create_optimized_server_script() {
    cat > ${INSTALL_DIR}/server.py << 'EOFPYTHON'
# server.py - 优化版服务器性能监控 API (兼容 Python 3.4+)
import json
import platform
import socket
import os
import sys
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import urllib.parse
from threading import Lock

class SystemMonitor:
    """系统监控类 - 优化版"""
    
    _cpu_cache = {'value': 0.0, 'timestamp': 0, 'lock': Lock()}
    _cache_duration = 1.0  # 缓存1秒
    
    @staticmethod
    def get_cpu_percent():
        """获取CPU使用率 - 带缓存优化"""
        try:
            now = time.time()
            with SystemMonitor._cpu_cache['lock']:
                # 使用缓存避免频繁计算
                if now - SystemMonitor._cpu_cache['timestamp'] < SystemMonitor._cache_duration:
                    return SystemMonitor._cpu_cache['value']
                
                if platform.system() == "Linux":
                    with open('/proc/stat', 'r') as f:
                        line = f.readline()
                    cpu_times1 = [int(x) for x in line.split()[1:8]]
                    
                    time.sleep(0.05)  # 减少等待时间从0.1到0.05
                    
                    with open('/proc/stat', 'r') as f:
                        line = f.readline()
                    cpu_times2 = [int(x) for x in line.split()[1:8]]
                    
                    deltas = [t2 - t1 for t1, t2 in zip(cpu_times1, cpu_times2)]
                    total = sum(deltas)
                    idle = deltas[3] if len(deltas) > 3 else 0
                    
                    if total > 0:
                        cpu_percent = 100.0 * (total - idle) / total
                    else:
                        cpu_percent = 0.0
                        
                    cpu_percent = round(cpu_percent, 2)
                else:
                    cpu_percent = 0.0
                
                # 更新缓存
                SystemMonitor._cpu_cache['value'] = cpu_percent
                SystemMonitor._cpu_cache['timestamp'] = now
                
                return cpu_percent
                
        except Exception as e:
            print(f"CPU Error: {e}", file=sys.stderr)
            return 0.0
    
    @staticmethod
    def get_memory_info():
        """获取内存信息"""
        try:
            if platform.system() == "Linux":
                with open('/proc/meminfo', 'r') as f:
                    lines = f.readlines()
                
                mem_info = {}
                for line in lines[:10]:  # 只读前10行，提高效率
                    parts = line.split(':')
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value_str = parts[1].strip().split()[0]
                        value = int(value_str) * 1024
                        mem_info[key] = value
                
                total = mem_info.get('MemTotal', 0)
                available = mem_info.get('MemAvailable', 0)
                used = total - available
                percent = (used / total * 100) if total > 0 else 0
                
                return {
                    'total': total,
                    'used': used,
                    'available': available,
                    'percent': round(percent, 2),
                    'total_gb': round(total / (1024**3), 2),
                    'used_gb': round(used / (1024**3), 2),
                    'available_gb': round(available / (1024**3), 2)
                }
            
            return {'error': 'Platform not supported'}
            
        except Exception as e:
            print(f"Memory Error: {e}", file=sys.stderr)
            return {'error': str(e)}
    
    @staticmethod
    def get_disk_info():
        """获取磁盘信息"""
        try:
            path = "/" if platform.system() != "Windows" else "C:\\"
            stat = os.statvfs(path)
            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bavail * stat.f_frsize
            used = total - free
            percent = (used / total * 100) if total > 0 else 0
            
            return {
                'total': total,
                'used': used,
                'free': free,
                'percent': round(percent, 2),
                'total_gb': round(total / (1024**3), 2),
                'used_gb': round(used / (1024**3), 2),
                'free_gb': round(free / (1024**3), 2)
            }
        except Exception as e:
            print(f"Disk Error: {e}", file=sys.stderr)
            return {'error': str(e)}
    
    @staticmethod
    def get_load_average():
        """获取系统负载"""
        try:
            if platform.system() != 'Windows':
                load1, load5, load15 = os.getloadavg()
                cpu_count = os.cpu_count() or 1
                
                return {
                    'load1': round(load1, 2),
                    'load5': round(load5, 2),
                    'load15': round(load15, 2),
                    'load1_percent': round((load1 / cpu_count) * 100, 2),
                    'load5_percent': round((load5 / cpu_count) * 100, 2),
                    'load15_percent': round((load15 / cpu_count) * 100, 2)
                }
            else:
                cpu_percent = SystemMonitor.get_cpu_percent()
                return {
                    'load1': cpu_percent,
                    'load5': cpu_percent,
                    'load15': cpu_percent,
                    'load1_percent': cpu_percent,
                    'load5_percent': cpu_percent,
                    'load15_percent': cpu_percent
                }
        except Exception as e:
            print(f"Load Error: {e}", file=sys.stderr)
            return {'error': str(e)}


class MonitorHandler(BaseHTTPRequestHandler):
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default_key')
    
    # 连接超时设置
    timeout = 30
    
    def verify_auth(self):
        """验证密钥"""
        auth_header = self.headers.get('Authorization')
        
        if not auth_header:
            return False
        
        try:
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
            else:
                token = auth_header
            
            return token == self.SECRET_KEY
        except Exception as e:
            print(f"Auth Error: {e}", file=sys.stderr)
            return False
    
    def send_unauthorized(self):
        """发送未授权响应"""
        self.send_json({
            'error': 'Unauthorized',
            'message': '未授权访问，请提供正确的 Bearer Token',
            'code': 401,
            'hint': 'Authorization: Bearer YOUR_SECRET_KEY'
        }, status_code=401)
    
    def do_GET(self):
        """处理GET请求"""
        try:
            client_ip = self.client_address[0]
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path
            
            # 简化日志输出
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] {client_ip} -> {path}", flush=True)
            
            # 所有路径都需要认证
            if not self.verify_auth():
                self.send_unauthorized()
                return
            
            routes = {
                '/': self.handle_root,
                '/health': self.handle_health,
                '/metrics': self.handle_metrics,
                '/cpu': self.handle_cpu,
                '/memory': self.handle_memory,
                '/disk': self.handle_disk,
                '/load': self.handle_load
            }
            
            handler = routes.get(path)
            if handler:
                handler()
            else:
                self.send_json({
                    'error': 'Not Found',
                    'path': path,
                    'available_paths': list(routes.keys())
                }, status_code=404)
                
        except Exception as e:
            print(f"Request Error: {e}", file=sys.stderr)
            try:
                self.send_json({
                    'error': 'Internal Server Error',
                    'message': str(e)
                }, status_code=500)
            except:
                pass
    
    def handle_root(self):
        """根路径"""
        help_info = {
            'service': 'Server Performance Monitor API',
            'version': '2.1-optimized',
            'status': 'running',
            'timestamp': datetime.now().isoformat(),
            'authentication': {
                'required': True,
                'type': 'Bearer Token',
                'header': 'Authorization: Bearer YOUR_SECRET_KEY'
            },
            'endpoints': {
                '/': 'API documentation',
                '/health': 'Health check',
                '/metrics': 'All metrics',
                '/cpu': 'CPU info',
                '/memory': 'Memory info',
                '/disk': 'Disk info',
                '/load': 'System load'
            }
        }
        self.send_json(help_info)
    
    def handle_health(self):
        """健康检查 - 快速响应"""
        self.send_json({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat()
        })
    
    def handle_metrics(self):
        """所有指标"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'cpu': {
                'percent': SystemMonitor.get_cpu_percent(),
                'count': os.cpu_count() or 1
            },
            'memory': SystemMonitor.get_memory_info(),
            'disk': SystemMonitor.get_disk_info(),
            'system': {
                'hostname': socket.gethostname(),
                'platform': platform.system(),
                'platform_release': platform.release(),
                'architecture': platform.machine()
            },
            'load': SystemMonitor.get_load_average()
        }
        self.send_json(data)
    
    def handle_cpu(self):
        """CPU信息"""
        self.send_json({
            'percent': SystemMonitor.get_cpu_percent(),
            'count': os.cpu_count() or 1,
            'timestamp': datetime.now().isoformat()
        })
    
    def handle_memory(self):
        """内存信息"""
        data = SystemMonitor.get_memory_info()
        data['timestamp'] = datetime.now().isoformat()
        self.send_json(data)
    
    def handle_disk(self):
        """磁盘信息"""
        data = SystemMonitor.get_disk_info()
        data['timestamp'] = datetime.now().isoformat()
        self.send_json(data)
    
    def handle_load(self):
        """负载信息"""
        data = SystemMonitor.get_load_average()
        data['timestamp'] = datetime.now().isoformat()
        self.send_json(data)
    
    def send_json(self, data, status_code=200):
        """发送JSON响应"""
        try:
            response = json.dumps(data, ensure_ascii=False, indent=2)
            response_bytes = response.encode('utf-8')
            
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', len(response_bytes))
            self.send_header('Connection', 'keep-alive')
            self.send_header('Keep-Alive', 'timeout=5, max=100')
            self.end_headers()
            self.wfile.write(response_bytes)
        except Exception as e:
            print(f"Response error: {e}", file=sys.stderr)
    
    def log_message(self, format, *args):
        """禁用默认日志"""
        pass


# 创建多线程 HTTP 服务器（兼容旧版本 Python）
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """支持多线程的 HTTP 服务器"""
    daemon_threads = True
    allow_reuse_address = True
    
    def server_bind(self):
        """绑定服务器并设置 socket 选项"""
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        HTTPServer.server_bind(self)


def run_server(host='0.0.0.0', port=None):
    """运行服务器 - 使用多线程"""
    if port is None:
        port = int(os.environ.get('LISTEN_PORT', 8627))
    
    print("\n" + "="*70)
    print("Server Performance Monitor API v2.1-optimized")
    print("="*70)
    print(f"Listening: {host}:{port}")
    print(f"Threading: Enabled (Multi-threaded)")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")
    
    try:
        # 使用自定义的多线程服务器
        httpd = ThreadedHTTPServer((host, port), MonitorHandler)
        
        print("Server ready to accept connections...\n")
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\nStopping...")
        httpd.shutdown()
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    run_server()
EOFPYTHON

    chmod +x ${INSTALL_DIR}/server.py
    print_success "优化版脚本创建完成"
}

# 交互式配置
interactive_config() {
    print_line
    echo -e "${CYAN}配置向导${NC}"
    print_line
    echo ""
    
    # 如果是重新安装且有现有配置
    if [[ "$IS_REINSTALL" == true ]] && [[ -f "$EXISTING_CONFIG" ]]; then
        source "$EXISTING_CONFIG"
        
        echo -e "${GREEN}检测到现有配置:${NC}"
        echo "  监听端口: ${LISTEN_PORT}"
        echo "  访问密钥: ${SECRET_KEY:0:8}********"
        echo ""
        
        read -p "$(echo -e ${CYAN}"是否使用现有配置? [Y/n]: "${NC})" use_existing
        
        if [[ ! "$use_existing" =~ ^[Nn]$ ]]; then
            print_success "使用现有配置"
            echo ""
            print_line
            echo -e "${GREEN}配置摘要:${NC}"
            echo "  安装目录: ${INSTALL_DIR}"
            echo "  监听端口: ${LISTEN_PORT}"
            echo "  访问密钥: ${SECRET_KEY}"
            print_line
            echo ""
            return 0
        fi
        
        echo ""
        print_info "将重新配置参数"
        echo ""
    fi
    
    # 配置端口
    while true; do
        read -p "$(echo -e ${CYAN}"请输入监听端口 [默认: 8627]: "${NC})" input_port
        
        if [[ -z "$input_port" ]]; then
            LISTEN_PORT=8627
            break
        elif [[ "$input_port" =~ ^[0-9]+$ ]] && [ "$input_port" -ge 1 ] && [ "$input_port" -le 65535 ]; then
            LISTEN_PORT=$input_port
            break
        else
            print_error "无效的端口号，请输入 1-65535 之间的数字"
        fi
    done
    
    print_success "监听端口设置为: ${LISTEN_PORT}"
    echo ""
    
    # 配置密钥
    RANDOM_KEY=$(generate_secret_key)
    echo -e "${CYAN}请配置 API 访问密钥:${NC}"
    echo -e "${YELLOW}提示: 留空将使用随机生成的密钥${NC}"
    echo -e "${YELLOW}随机密钥: ${RANDOM_KEY}${NC}"
    echo ""
    
    read -p "$(echo -e ${CYAN}"请输入密钥 [留空使用随机密钥]: "${NC})" input_key
    
    if [[ -z "$input_key" ]]; then
        SECRET_KEY=$RANDOM_KEY
        print_success "使用随机生成的密钥"
    else
        SECRET_KEY=$input_key
        print_success "使用自定义密钥"
    fi
    
    echo ""
    print_line
    echo -e "${GREEN}配置摘要:${NC}"
    echo "  安装目录: ${INSTALL_DIR}"
    echo "  监听端口: ${LISTEN_PORT}"
    echo "  访问密钥: ${SECRET_KEY}"
    print_line
    echo ""
    
    read -p "$(echo -e ${CYAN}"确认安装? [y/N]: "${NC})" confirm
    
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_warning "安装已取消"
        exit 0
    fi
    
    echo ""
}

# 创建安装目录
create_directory() {
    print_step "创建安装目录: ${INSTALL_DIR}"
    
    if [[ -d $INSTALL_DIR ]]; then
        print_warning "目录已存在"
        read -p "$(echo -e ${YELLOW}"是否备份现有文件? [Y/n]: "${NC})" backup_confirm
        
        if [[ ! "$backup_confirm" =~ ^[Nn]$ ]]; then
            BACKUP_DIR="${INSTALL_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
            mv $INSTALL_DIR $BACKUP_DIR
            print_success "已备份到: ${BACKUP_DIR}"
        else
            rm -rf $INSTALL_DIR
            print_info "已删除旧目录"
        fi
    fi
    
    mkdir -p $INSTALL_DIR
    print_success "目录创建完成"
}

# 创建配置文件
create_config() {
    print_step "创建配置文件..."
    
    cat > ${INSTALL_DIR}/config.env << EOF
# Server Monitor Configuration
LISTEN_PORT=${LISTEN_PORT}
SECRET_KEY=${SECRET_KEY}
EOF

    chmod 600 ${INSTALL_DIR}/config.env
    print_success "配置文件创建完成"
}

# 创建 systemd 服务
create_service() {
    print_step "创建 systemd 服务..."
    
    cat > ${SERVICE_FILE} << EOF
[Unit]
Description=Server Performance Monitor API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=${INSTALL_DIR}

EnvironmentFile=${INSTALL_DIR}/config.env
Environment="PYTHONUNBUFFERED=1"

ExecStart=/usr/bin/python3 ${INSTALL_DIR}/server.py

Restart=always
RestartSec=10

StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

PrivateTmp=true
NoNewPrivileges=true
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

    print_success "systemd 服务文件创建完成"
}

# 启动服务
start_service() {
    print_step "启动服务..."
    
    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME}.service
    systemctl start ${SERVICE_NAME}.service
    
    sleep 2
    
    if systemctl is-active --quiet ${SERVICE_NAME}.service; then
        print_success "服务启动成功"
    else
        print_error "服务启动失败"
        print_info "查看日志: journalctl -u ${SERVICE_NAME} -n 50"
        exit 1
    fi
}

# 测试服务
test_service() {
    print_step "测试服务..."
    
    sleep 2
    
    if command -v curl &> /dev/null; then
        print_info "测试 API 连接..."
        RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${SECRET_KEY}" http://localhost:${LISTEN_PORT}/health)
        if [[ "$RESPONSE" == "200" ]]; then
            print_success "API 测试成功 (HTTP 200)"
        else
            print_warning "API 测试失败，响应码: $RESPONSE"
        fi
    else
        print_warning "curl 未安装，跳过 API 测试"
    fi
}

# 显示安装信息
show_info() {
    echo ""
    print_line
    echo -e "${GREEN}✓ 安装完成！${NC}"
    print_line
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}服务信息${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo "  服务名称: ${SERVICE_NAME}"
    echo "  安装目录: ${INSTALL_DIR}"
    echo "  监听端口: ${LISTEN_PORT}"
    echo "  配置文件: ${INSTALL_DIR}/config.env"
    echo "  访问密钥: ${SECRET_KEY}"
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}服务管理${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo "  启动: systemctl start ${SERVICE_NAME}"
    echo "  停止: systemctl stop ${SERVICE_NAME}"
    echo "  重启: systemctl restart ${SERVICE_NAME}"
    echo "  状态: systemctl status ${SERVICE_NAME}"
    echo "  日志: journalctl -u ${SERVICE_NAME} -f"
    echo "  管理: ${INSTALL_DIR}/manage.sh"
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}API 访问示例${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  # 健康检查"
    echo "  curl -H \"Authorization: Bearer ${SECRET_KEY}\" \\"
    echo "       http://localhost:${LISTEN_PORT}/health"
    echo ""
    echo "  # 获取所有指标"
    echo "  curl -H \"Authorization: Bearer ${SECRET_KEY}\" \\"
    echo "       http://localhost:${LISTEN_PORT}/metrics"
    echo ""
    echo "  # CPU 信息"
    echo "  curl -H \"Authorization: Bearer ${SECRET_KEY}\" \\"
    echo "       http://localhost:${LISTEN_PORT}/cpu"
    echo ""
    echo "  # 格式化输出"
    echo "  curl -H \"Authorization: Bearer ${SECRET_KEY}\" \\"
    echo "       http://localhost:${LISTEN_PORT}/metrics | jq ."
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}重要提示${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo "  🔒 所有接口都需要 Bearer Token 认证"
    echo "  🔑 密钥存储在: ${INSTALL_DIR}/config.env (权限 600)"
    echo "  ⚙️  修改配置后需重启服务"
    echo "  🛠️  使用管理工具: sudo ${INSTALL_DIR}/manage.sh"
    echo "  🗑️  卸载服务: sudo ${INSTALL_DIR}/uninstall.sh"
    echo ""
    if command -v firewall-cmd &> /dev/null && systemctl is-active --quiet firewalld; then
        echo -e "${YELLOW}  ⚠️  防火墙提示:${NC}"
        echo "     firewall-cmd --permanent --add-port=${LISTEN_PORT}/tcp"
        echo "     firewall-cmd --reload"
        echo ""
    fi
    print_line
    echo ""
}

# 创建卸载脚本
create_uninstall_script() {
    print_step "创建卸载脚本..."
    
    cat > ${INSTALL_DIR}/uninstall.sh << 'EOFUNINSTALL'
#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SERVICE_NAME="server-monitor"
INSTALL_DIR="/usr/local/server-monitor"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo -e "${YELLOW}开始卸载 Server Monitor...${NC}\n"

if systemctl is-active --quiet ${SERVICE_NAME}; then
    echo -e "${GREEN}[1/5]${NC} 停止服务..."
    systemctl stop ${SERVICE_NAME}
fi

if systemctl is-enabled --quiet ${SERVICE_NAME} 2>/dev/null; then
    echo -e "${GREEN}[2/5]${NC} 禁用服务..."
    systemctl disable ${SERVICE_NAME}
fi

if [[ -f $SERVICE_FILE ]]; then
    echo -e "${GREEN}[3/5]${NC} 删除服务文件..."
    rm -f $SERVICE_FILE
    systemctl daemon-reload
fi

if [[ -f ${INSTALL_DIR}/config.env ]]; then
    echo -e "${GREEN}[4/5]${NC} 备份配置..."
    BACKUP_FILE="/tmp/server-monitor-config-$(date +%Y%m%d_%H%M%S).env"
    cp ${INSTALL_DIR}/config.env $BACKUP_FILE
    echo -e "      ${GREEN}✓${NC} 配置已备份到: $BACKUP_FILE"
fi

if [[ -d $INSTALL_DIR ]]; then
    echo -e "${GREEN}[5/5]${NC} 删除安装目录..."
    rm -rf $INSTALL_DIR
fi

echo ""
echo -e "${GREEN}卸载完成！${NC}"
EOFUNINSTALL

    chmod +x ${INSTALL_DIR}/uninstall.sh
    print_success "卸载脚本创建完成"
}

# 创建管理脚本
create_management_script() {
    print_step "创建管理脚本..."
    
    cat > ${INSTALL_DIR}/manage.sh << 'EOFMANAGE'
#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SERVICE_NAME="server-monitor"
INSTALL_DIR="/usr/local/server-monitor"
CONFIG_FILE="${INSTALL_DIR}/config.env"

show_menu() {
    clear
    echo -e "${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║     Server Monitor 管理工具 v2.3                  ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
    echo ""
    
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        echo -e "${GREEN}● 服务状态: 运行中${NC}"
    else
        echo -e "${RED}● 服务状态: 已停止${NC}"
    fi
    
    if [[ -f $CONFIG_FILE ]]; then
        source $CONFIG_FILE
        echo -e "${CYAN}● 监听端口: ${LISTEN_PORT}${NC}"
        echo -e "${CYAN}● 访问密钥: ${SECRET_KEY:0:8}********${NC}"
    fi
    
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}服务管理:${NC}"
    echo "  1) 启动服务"
    echo "  2) 停止服务"
    echo "  3) 重启服务"
    echo "  4) 查看状态"
    echo "  5) 查看实时日志"
    echo "  6) 查看历史日志"
    echo ""
    echo -e "${YELLOW}配置管理:${NC}"
    echo "  7) 查看完整配置"
    echo "  8) 修改监听端口"
    echo "  9) 更新访问密钥"
    echo "  10) 生成新随机密钥"
    echo "  11) 查看当前密钥"
    echo ""
    echo -e "${YELLOW}测试与诊断:${NC}"
    echo "  12) 测试 API 连接"
    echo "  13) 检查端口占用"
    echo "  14) 查看进程信息"
    echo ""
    echo -e "${YELLOW}其他操作:${NC}"
    echo "  15) 启用开机自启"
    echo "  16) 禁用开机自启"
    echo "  17) 卸载服务"
    echo ""
    echo "  0) 退出"
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
}

start_service() {
    echo -e "${BLUE}正在启动服务...${NC}"
    systemctl start ${SERVICE_NAME}
    sleep 2
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        echo -e "${GREEN}✓ 服务启动成功${NC}"
    else
        echo -e "${RED}✗ 服务启动失败${NC}"
        journalctl -u ${SERVICE_NAME} -n 20 --no-pager
    fi
}

stop_service() {
    echo -e "${BLUE}正在停止服务...${NC}"
    systemctl stop ${SERVICE_NAME}
    sleep 1
    if ! systemctl is-active --quiet ${SERVICE_NAME}; then
        echo -e "${GREEN}✓ 服务已停止${NC}"
    else
        echo -e "${RED}✗ 服务停止失败${NC}"
    fi
}

restart_service() {
    echo -e "${BLUE}正在重启服务...${NC}"
    systemctl restart ${SERVICE_NAME}
    sleep 2
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        echo -e "${GREEN}✓ 服务重启成功${NC}"
    else
        echo -e "${RED}✗ 服务重启失败${NC}"
        journalctl -u ${SERVICE_NAME} -n 20 --no-pager
    fi
}

show_status() {
    echo -e "${BLUE}服务详细状态:${NC}\n"
    systemctl status ${SERVICE_NAME} --no-pager
    echo ""
    if systemctl is-enabled --quiet ${SERVICE_NAME} 2>/dev/null; then
        echo -e "${GREEN}● 开机自启: 已启用${NC}"
    else
        echo -e "${YELLOW}● 开机自启: 未启用${NC}"
    fi
}

show_logs_follow() {
    echo -e "${BLUE}查看实时日志 (按 Ctrl+C 退出)...${NC}\n"
    sleep 1
    journalctl -u ${SERVICE_NAME} -f
}

show_logs_recent() {
    echo -e "${BLUE}最近 100 行日志:${NC}\n"
    journalctl -u ${SERVICE_NAME} -n 100 --no-pager
}

show_config() {
    echo -e "${BLUE}当前配置信息:${NC}\n"
    if [[ -f $CONFIG_FILE ]]; then
        cat $CONFIG_FILE
    else
        echo -e "${RED}✗ 配置文件不存在${NC}"
    fi
}

change_port() {
    if [[ ! -f $CONFIG_FILE ]]; then
        echo -e "${RED}✗ 配置文件不存在${NC}"
        return
    fi
    
    current_port=$(grep "^LISTEN_PORT=" $CONFIG_FILE | cut -d'=' -f2)
    echo -e "${YELLOW}当前端口: ${current_port}${NC}\n"
    
    while true; do
        read -p "请输入新端口 [1-65535]: " new_port
        
        if [[ "$new_port" =~ ^[0-9]+$ ]] && [ "$new_port" -ge 1 ] && [ "$new_port" -le 65535 ]; then
            break
        else
            echo -e "${RED}✗ 无效的端口号${NC}"
        fi
    done
    
    sed -i "s/^LISTEN_PORT=.*/LISTEN_PORT=${new_port}/" $CONFIG_FILE
    echo -e "${GREEN}✓ 端口已更新为: ${new_port}${NC}"
    echo -e "${YELLOW}! 需要重启服务才能生效${NC}\n"
    
    read -p "是否现在重启服务? [y/N]: " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        restart_service
    fi
}

update_secret_key() {
    if [[ ! -f $CONFIG_FILE ]]; then
        echo -e "${RED}✗ 配置文件不存在${NC}"
        return
    fi
    
    source $CONFIG_FILE
    
    echo -e "${CYAN}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║              更新访问密钥                          ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}当前密钥: ${SECRET_KEY}${NC}\n"
    
    echo -e "${BLUE}提示:${NC}"
    echo "  - 密钥长度建议 16-64 个字符"
    echo "  - 可使用字母、数字、特殊字符"
    echo "  - 留空取消修改"
    echo ""
    
    while true; do
        read -p "$(echo -e ${CYAN}"请输入新密钥: "${NC})" new_key
        
        if [[ -z "$new_key" ]]; then
            echo -e "${YELLOW}✗ 已取消修改${NC}"
            return
        fi
        
        if [[ ${#new_key} -lt 8 ]]; then
            echo -e "${RED}✗ 密钥长度不能少于 8 个字符${NC}"
            continue
        fi
        
        if [[ ${#new_key} -gt 128 ]]; then
            echo -e "${RED}✗ 密钥长度不能超过 128 个字符${NC}"
            continue
        fi
        
        break
    done
    
    echo ""
    echo -e "${YELLOW}新密钥: ${new_key}${NC}"
    read -p "$(echo -e ${CYAN}"确认更新密钥? [y/N]: "${NC})" confirm
    
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}✗ 已取消修改${NC}"
        return
    fi
    
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=${new_key}/" $CONFIG_FILE
    
    echo ""
    echo -e "${GREEN}✓ 密钥已成功更新${NC}"
    echo -e "${CYAN}新密钥: ${new_key}${NC}"
    echo -e "${YELLOW}! 需要重启服务才能生效${NC}\n"
    
    if [[ -f $CONFIG_FILE ]]; then
        source $CONFIG_FILE
        echo -e "${BLUE}测试命令:${NC}"
        echo "  curl -H \"Authorization: Bearer ${new_key}\" \\"
        echo "       http://localhost:${LISTEN_PORT}/health"
        echo ""
    fi
    
    read -p "是否现在重启服务? [y/N]: " restart_confirm
    if [[ "$restart_confirm" =~ ^[Yy]$ ]]; then
        restart_service
    fi
}

generate_new_secret() {
    if [[ ! -f $CONFIG_FILE ]]; then
        echo -e "${RED}✗ 配置文件不存在${NC}"
        return
    fi
    
    source $CONFIG_FILE
    
    echo -e "${CYAN}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║            生成新随机密钥                          ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}当前密钥: ${SECRET_KEY}${NC}\n"
    
    echo -e "${GREEN}随机生成的密钥候选:${NC}\n"
    
    keys=()
    for i in {1..5}; do
        random_key=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 32 | head -n 1)
        keys+=("$random_key")
        echo "  ${i}) ${random_key}"
    done
    
    echo ""
    echo "  6) 生成更多选项"
    echo "  7) 自定义长度密钥"
    echo "  0) 取消"
    echo ""
    
    while true; do
        read -p "$(echo -e ${CYAN}"请选择密钥 [0-7]: "${NC})" choice
        
        case $choice in
            1|2|3|4|5)
                new_key="${keys[$((choice-1))]}"
                break
                ;;
            6)
                generate_new_secret
                return
                ;;
            7)
                read -p "$(echo -e ${CYAN}"请输入密钥长度 [16-64]: "${NC})" key_length
                
                if [[ ! "$key_length" =~ ^[0-9]+$ ]] || [ "$key_length" -lt 16 ] || [ "$key_length" -gt 64 ]; then
                    echo -e "${RED}✗ 无效的长度，使用默认 32${NC}"
                    key_length=32
                fi
                
                new_key=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w $key_length | head -n 1)
                break
                ;;
            0)
                echo -e "${YELLOW}✗ 已取消${NC}"
                return
                ;;
            *)
                echo -e "${RED}✗ 无效选择${NC}"
                ;;
        esac
    done
    
    echo ""
    echo -e "${GREEN}选中的新密钥:${NC}"
    echo -e "${CYAN}${new_key}${NC}\n"
    
    read -p "$(echo -e ${CYAN}"确认使用此密钥? [y/N]: "${NC})" confirm
    
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}✗ 已取消${NC}"
        return
    fi
    
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=${new_key}/" $CONFIG_FILE
    
    echo ""
    echo -e "${GREEN}✓ 密钥已成功更新${NC}"
    echo -e "${CYAN}新密钥: ${new_key}${NC}"
    echo -e "${YELLOW}⚠️  请妥善保存此密钥！${NC}"
    echo -e "${YELLOW}! 需要重启服务才能生效${NC}\n"
    
    if [[ -f $CONFIG_FILE ]]; then
        source $CONFIG_FILE
        echo -e "${BLUE}测试命令:${NC}"
        echo "  curl -H \"Authorization: Bearer ${new_key}\" \\"
        echo "       http://localhost:${LISTEN_PORT}/health"
        echo ""
    fi
    
    read -p "是否现在重启服务? [y/N]: " restart_confirm
    if [[ "$restart_confirm" =~ ^[Yy]$ ]]; then
        restart_service
    fi
}

show_current_key() {
    if [[ ! -f $CONFIG_FILE ]]; then
        echo -e "${RED}✗ 配置文件不存在${NC}"
        return
    fi
    
    source $CONFIG_FILE
    
    echo -e "${CYAN}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║              当前访问密钥                          ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${GREEN}完整密钥:${NC}"
    echo -e "${YELLOW}${SECRET_KEY}${NC}\n"
    
    echo -e "${BLUE}使用示例:${NC}"
    echo ""
    echo "# 健康检查"
    echo "curl -H \"Authorization: Bearer ${SECRET_KEY}\" \\"
    echo "     http://localhost:${LISTEN_PORT}/health"
    echo ""
    echo "# 获取所有指标"
    echo "curl -H \"Authorization: Bearer ${SECRET_KEY}\" \\"
    echo "     http://localhost:${LISTEN_PORT}/metrics"
    echo ""
    
    echo -e "${CYAN}提示: 选中文本即可复制${NC}"
    echo ""
    
    read -p "按 Enter 键继续..." dummy
}

test_api() {
    if ! command -v curl &> /dev/null; then
        echo -e "${RED}✗ curl 未安装${NC}"
        return
    fi
    
    if [[ ! -f $CONFIG_FILE ]]; then
        echo -e "${RED}✗ 配置文件不存在${NC}"
        return
    fi
    
    source $CONFIG_FILE
    
    echo -e "${BLUE}测试 API 连接...${NC}\n"
    
    echo -e "${CYAN}1. 测试健康检查${NC}"
    HTTP_CODE=$(curl -s -H "Authorization: Bearer ${SECRET_KEY}" \
        -o /tmp/api_response.json -w "%{http_code}" \
        http://localhost:${LISTEN_PORT}/health)
    
    if command -v python3 &> /dev/null; then
        cat /tmp/api_response.json | python3 -m json.tool 2>/dev/null || cat /tmp/api_response.json
    else
        cat /tmp/api_response.json
    fi
    echo ""
    
    if [[ "$HTTP_CODE" == "200" ]]; then
        echo -e "${GREEN}✓ HTTP Status: $HTTP_CODE (成功)${NC}\n"
    else
        echo -e "${RED}✗ HTTP Status: $HTTP_CODE (失败)${NC}\n"
    fi
    
    echo -e "${CYAN}2. 测试 CPU 信息${NC}"
    curl -s -H "Authorization: Bearer ${SECRET_KEY}" \
        http://localhost:${LISTEN_PORT}/cpu | python3 -m json.tool 2>/dev/null || \
        curl -s -H "Authorization: Bearer ${SECRET_KEY}" http://localhost:${LISTEN_PORT}/cpu
    
    echo -e "\n${GREEN}✓ API 测试完成${NC}"
    rm -f /tmp/api_response.json
}

check_port() {
    if [[ ! -f $CONFIG_FILE ]]; then
        echo -e "${RED}✗ 配置文件不存在${NC}"
        return
    fi
    
    source $CONFIG_FILE
    
    echo -e "${BLUE}检查端口 ${LISTEN_PORT} 占用情况...${NC}\n"
    
    if command -v ss &> /dev/null; then
        ss -tuln | grep ":${LISTEN_PORT}"
    elif command -v netstat &> /dev/null; then
        netstat -tuln | grep ":${LISTEN_PORT}"
    else
        echo -e "${YELLOW}! 未找到 ss 或 netstat 命令${NC}"
    fi
}

show_process() {
    echo -e "${BLUE}查看服务进程信息...${NC}\n"
    
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        MAIN_PID=$(systemctl show -p MainPID --value ${SERVICE_NAME})
        
        if [[ -n "$MAIN_PID" && "$MAIN_PID" != "0" ]]; then
            echo -e "${CYAN}主进程 PID: ${MAIN_PID}${NC}\n"
            ps -fp $MAIN_PID
        else
            echo -e "${RED}✗ 无法获取进程信息${NC}"
        fi
    else
        echo -e "${RED}✗ 服务未运行${NC}"
    fi
}

enable_autostart() {
    echo -e "${BLUE}启用开机自启...${NC}"
    systemctl enable ${SERVICE_NAME}
    if systemctl is-enabled --quiet ${SERVICE_NAME} 2>/dev/null; then
        echo -e "${GREEN}✓ 已启用开机自启${NC}"
    else
        echo -e "${RED}✗ 启用失败${NC}"
    fi
}

disable_autostart() {
    echo -e "${BLUE}禁用开机自启...${NC}"
    systemctl disable ${SERVICE_NAME}
    if ! systemctl is-enabled --quiet ${SERVICE_NAME} 2>/dev/null; then
        echo -e "${GREEN}✓ 已禁用开机自启${NC}"
    else
        echo -e "${RED}✗ 禁用失败${NC}"
    fi
}

uninstall_service() {
    echo ""
    echo -e "${RED}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║                  警 告                             ║${NC}"
    echo -e "${RED}╚═══════════════════════════════════════════════════╝${NC}"
    echo -e "${YELLOW}这将完全卸载 Server Monitor 服务！${NC}\n"
    
    read -p "确认卸载? 输入 'YES' 继续: " confirm
    
    if [[ "$confirm" == "YES" ]]; then
        if [[ -f ${INSTALL_DIR}/uninstall.sh ]]; then
            echo ""
            bash ${INSTALL_DIR}/uninstall.sh
            exit 0
        else
            echo -e "${RED}✗ 卸载脚本不存在${NC}"
        fi
    else
        echo -e "${YELLOW}已取消卸载${NC}"
    fi
}

main() {
    while true; do
        show_menu
        read -p "请选择操作 [0-17]: " choice
        echo ""
        
        case $choice in
            1) start_service ;;
            2) stop_service ;;
            3) restart_service ;;
            4) show_status ;;
            5) show_logs_follow ;;
            6) show_logs_recent ;;
            7) show_config ;;
            8) change_port ;;
            9) update_secret_key ;;
            10) generate_new_secret ;;
            11) show_current_key ;;
            12) test_api ;;
            13) check_port ;;
            14) show_process ;;
            15) enable_autostart ;;
            16) disable_autostart ;;
            17) uninstall_service ;;
            0) 
                echo -e "${GREEN}再见！${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}✗ 无效的选择，请输入 0-17${NC}"
                ;;
        esac
        
        echo ""
        read -p "按 Enter 键继续..."
    done
}

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}✗ 此脚本需要 root 权限运行${NC}"
    echo "请使用: sudo \$0"
    exit 1
fi

main
EOFMANAGE

    chmod +x ${INSTALL_DIR}/manage.sh
    print_success "管理脚本创建完成"
}

# 主函数
main() {
    print_banner
    
    check_root
    check_os
    check_python
    check_systemd
    
    check_existing_installation
    
    interactive_config
    
    if [[ "$IS_REINSTALL" != true ]]; then
        create_directory
    else
        mkdir -p $INSTALL_DIR
    fi
    
    create_optimized_server_script
    create_config
    create_service
    create_uninstall_script
    create_management_script
    
    start_service
    test_service
    
    show_info
    
    print_info "您可以使用以下命令管理服务:"
    echo -e "  ${CYAN}sudo ${INSTALL_DIR}/manage.sh${NC}"
    echo ""
}

# 执行主函数
main

exit 0
