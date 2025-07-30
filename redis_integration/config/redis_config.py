"""
Redis Configuration for XMRT-Ecosystem

Configuration management for Redis connections and cache settings.
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class RedisConfig:
    """Redis configuration settings"""
    
    # Connection settings
    host: str = os.getenv('REDIS_HOST', 'localhost')
    port: int = int(os.getenv('REDIS_PORT', '6379'))
    database: int = int(os.getenv('REDIS_DB', '0'))
    password: Optional[str] = os.getenv('REDIS_PASSWORD')
    
    # Connection pool settings
    max_connections: int = int(os.getenv('REDIS_MAX_CONNECTIONS', '20'))
    socket_timeout: float = float(os.getenv('REDIS_SOCKET_TIMEOUT', '5.0'))
    connect_timeout: float = float(os.getenv('REDIS_CONNECT_TIMEOUT', '5.0'))
    
    # Cache settings
    key_prefix: str = os.getenv('REDIS_KEY_PREFIX', 'xmrt:')
    default_ttl: int = int(os.getenv('REDIS_DEFAULT_TTL', '3600'))
    max_memory_policy: str = os.getenv('REDIS_MAX_MEMORY_POLICY', 'allkeys-lru')
    
    # Pub/Sub settings
    pubsub_timeout: float = float(os.getenv('REDIS_PUBSUB_TIMEOUT', '1.0'))
    
    # Cluster settings (if using Redis Cluster)
    cluster_enabled: bool = os.getenv('REDIS_CLUSTER_ENABLED', 'false').lower() == 'true'
    cluster_nodes: Optional[str] = os.getenv('REDIS_CLUSTER_NODES')
    
    # SSL/TLS settings
    ssl_enabled: bool = os.getenv('REDIS_SSL_ENABLED', 'false').lower() == 'true'
    ssl_cert_file: Optional[str] = os.getenv('REDIS_SSL_CERT_FILE')
    ssl_key_file: Optional[str] = os.getenv('REDIS_SSL_KEY_FILE')
    ssl_ca_file: Optional[str] = os.getenv('REDIS_SSL_CA_FILE')
    
    def get_connection_url(self) -> str:
        """Get Redis connection URL"""
        auth = f":{self.password}@" if self.password else ""
        protocol = "rediss" if self.ssl_enabled else "redis"
        return f"{protocol}://{auth}{self.host}:{self.port}/{self.database}"
    
    def get_cluster_nodes(self) -> list:
        """Get cluster nodes list"""
        if not self.cluster_nodes:
            return []
        
        nodes = []
        for node in self.cluster_nodes.split(','):
            host, port = node.strip().split(':')
            nodes.append({'host': host, 'port': int(port)})
        
        return nodes
    
    def validate(self) -> bool:
        """Validate configuration settings"""
        if self.port < 1 or self.port > 65535:
            raise ValueError("Invalid Redis port number")
        
        if self.database < 0:
            raise ValueError("Invalid Redis database number")
        
        if self.max_connections < 1:
            raise ValueError("Invalid max connections value")
        
        if self.cluster_enabled and not self.cluster_nodes:
            raise ValueError("Cluster nodes must be specified when cluster is enabled")
        
        return True


# Default configuration instance
default_config = RedisConfig()


# Environment-specific configurations
class DevelopmentConfig(RedisConfig):
    """Development environment configuration"""
    def __init__(self):
        super().__init__()
        self.key_prefix = 'xmrt:dev:'
        self.default_ttl = 1800  # 30 minutes


class ProductionConfig(RedisConfig):
    """Production environment configuration"""
    def __init__(self):
        super().__init__()
        self.key_prefix = 'xmrt:prod:'
        self.default_ttl = 7200  # 2 hours
        self.max_connections = 50


class TestingConfig(RedisConfig):
    """Testing environment configuration"""
    def __init__(self):
        super().__init__()
        self.database = 15  # Use separate DB for tests
        self.key_prefix = 'xmrt:test:'
        self.default_ttl = 300  # 5 minutes


def get_config(environment: str = None) -> RedisConfig:
    """Get configuration based on environment"""
    env = environment or os.getenv('ENVIRONMENT', 'development').lower()
    
    if env == 'production':
        return ProductionConfig()
    elif env == 'testing':
        return TestingConfig()
    else:
        return DevelopmentConfig()


# Configuration validation
def validate_redis_connection(config: RedisConfig) -> bool:
    """Validate Redis connection with given configuration"""
    import redis
    
    try:
        client = redis.Redis(
            host=config.host,
            port=config.port,
            db=config.database,
            password=config.password,
            socket_timeout=config.socket_timeout,
            socket_connect_timeout=config.connect_timeout
        )
        
        # Test connection
        client.ping()
        client.close()
        return True
        
    except Exception as e:
        print(f"Redis connection validation failed: {e}")
        return False

