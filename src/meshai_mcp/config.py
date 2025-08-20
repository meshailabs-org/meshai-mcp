"""
Configuration Management for MeshAI Gateway Service

Handles environment-specific configuration loading with validation.
"""

import os
import yaml
from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog
from pydantic import BaseModel, Field, validator

logger = structlog.get_logger(__name__)


class ServiceConfig(BaseModel):
    """Configuration for external services"""
    auth_service_url: str = "http://localhost:8000"
    agent_registry_url: str = "http://localhost:8001"
    workflow_engine_url: str = "http://localhost:8002"


class PerformanceConfig(BaseModel):
    """Performance-related configuration"""
    request_timeout_seconds: int = 120
    max_concurrent_requests: int = 200
    rate_limit_per_minute: int = 1000


class SecurityConfig(BaseModel):
    """Security configuration"""
    require_https: bool = True
    allowed_origins: List[str] = ["*"]


class DatabaseConfig(BaseModel):
    """Database configuration"""
    use_in_memory: bool = False
    redis_url: Optional[str] = None
    postgres_url: Optional[str] = None


class MonitoringConfig(BaseModel):
    """Monitoring and observability configuration"""
    enable_metrics: bool = True
    metrics_endpoint: str = "/metrics"
    health_check_interval_seconds: int = 30


class ScalingConfig(BaseModel):
    """Scaling configuration"""
    min_instances: int = 0
    max_instances: int = 10
    cpu_utilization_target: int = 70
    memory_utilization_target: int = 80


class CloudRunConfig(BaseModel):
    """Cloud Run specific configuration"""
    service_name: str = "meshai-gateway-service"
    region: str = "us-central1"
    memory: str = "1Gi"
    cpu: str = "1000m"
    concurrency: int = 80
    timeout: int = 300


class AgentDefinition(BaseModel):
    """Agent definition"""
    agent_id: str
    name: str
    framework: str
    status: str = "active"


class WorkflowDefinition(BaseModel):
    """Workflow definition"""
    workflow_id: str
    name: str
    description: str
    agents: List[str]
    routing_strategy: str = "collaborative"
    timeout_seconds: int = 300


class GatewayConfig(BaseModel):
    """Complete gateway configuration"""
    debug: bool = False
    log_level: str = "INFO"
    
    services: ServiceConfig = Field(default_factory=ServiceConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    scaling: ScalingConfig = Field(default_factory=ScalingConfig)
    cloud_run: CloudRunConfig = Field(default_factory=CloudRunConfig)
    
    default_agents: List[AgentDefinition] = Field(default_factory=list)
    default_workflows: List[WorkflowDefinition] = Field(default_factory=list)
    
    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of {valid_levels}')
        return v.upper()


class ConfigLoader:
    """Configuration loader with environment support"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or self._find_config_file()
        self.environment = os.getenv('MESHAI_ENVIRONMENT', 'development')
        
    def _find_config_file(self) -> str:
        """Find the configuration file"""
        # Look for config file in common locations
        possible_paths = [
            'gateway-config.yaml',
            'config/gateway-config.yaml',
            '../gateway-config.yaml',
            os.path.join(Path(__file__).parent.parent.parent, 'gateway-config.yaml')
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
                
        logger.warning("No config file found, using defaults")
        return None
    
    def load(self) -> GatewayConfig:
        """Load configuration for the current environment"""
        
        config_data = {}
        
        # Load from file if available
        if self.config_file and os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    all_config = yaml.safe_load(f)
                    
                if self.environment in all_config:
                    config_data = all_config[self.environment]
                    logger.info(f"Loaded config for environment: {self.environment}")
                else:
                    logger.warning(f"Environment '{self.environment}' not found in config, using defaults")
                    
            except Exception as e:
                logger.error(f"Error loading config file: {e}")
        
        # Override with environment variables
        config_data = self._apply_environment_overrides(config_data)
        
        # Load default agents and workflows if available
        if self.config_file and os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    all_config = yaml.safe_load(f)
                    
                if 'agents' in all_config and 'default_agents' in all_config['agents']:
                    config_data['default_agents'] = [
                        AgentDefinition(**agent) for agent in all_config['agents']['default_agents']
                    ]
                    
                if 'workflows' in all_config and 'default_workflows' in all_config['workflows']:
                    config_data['default_workflows'] = [
                        WorkflowDefinition(**workflow) for workflow in all_config['workflows']['default_workflows']
                    ]
                    
            except Exception as e:
                logger.error(f"Error loading agents/workflows: {e}")
        
        # Create and validate configuration
        try:
            config = GatewayConfig(**config_data)
            logger.info("Configuration loaded successfully", environment=self.environment)
            return config
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            # Return default configuration
            return GatewayConfig()
    
    def _apply_environment_overrides(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides"""
        
        # Environment variable mappings
        env_mappings = {
            'DEBUG': 'debug',
            'MESHAI_LOG_LEVEL': 'log_level',
            'MESHAI_AUTH_SERVICE_URL': 'services.auth_service_url',
            'MESHAI_AGENT_REGISTRY_URL': 'services.agent_registry_url',
            'MESHAI_WORKFLOW_ENGINE_URL': 'services.workflow_engine_url',
            'REQUEST_TIMEOUT_SECONDS': 'performance.request_timeout_seconds',
            'MAX_CONCURRENT_REQUESTS': 'performance.max_concurrent_requests',
            'RATE_LIMIT_PER_MINUTE': 'performance.rate_limit_per_minute',
            'REQUIRE_HTTPS': 'security.require_https',
            'REDIS_URL': 'database.redis_url',
            'DATABASE_URL': 'database.postgres_url',
            'USE_IN_MEMORY': 'database.use_in_memory',
            'ENABLE_METRICS': 'monitoring.enable_metrics',
            'MIN_INSTANCES': 'scaling.min_instances',
            'MAX_INSTANCES': 'scaling.max_instances'
        }
        
        for env_var, config_path in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                self._set_nested_config(config_data, config_path, self._convert_env_value(env_value))
        
        # Handle special cases
        allowed_origins = os.getenv('ALLOWED_ORIGINS')
        if allowed_origins:
            origins = [origin.strip() for origin in allowed_origins.split(',')]
            self._set_nested_config(config_data, 'security.allowed_origins', origins)
        
        return config_data
    
    def _set_nested_config(self, config: Dict[str, Any], path: str, value: Any):
        """Set a nested configuration value"""
        keys = path.split('.')
        current = config
        
        # Navigate to parent
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Set value
        current[keys[-1]] = value
    
    def _convert_env_value(self, value: str) -> Any:
        """Convert environment variable string to appropriate type"""
        
        # Boolean values
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        # Integer values
        try:
            return int(value)
        except ValueError:
            pass
        
        # Float values
        try:
            return float(value)
        except ValueError:
            pass
        
        # String value (default)
        return value


def load_config() -> GatewayConfig:
    """Load configuration for the current environment"""
    loader = ConfigLoader()
    return loader.load()


def get_environment() -> str:
    """Get the current environment name"""
    return os.getenv('MESHAI_ENVIRONMENT', 'development')


def is_production() -> bool:
    """Check if running in production environment"""
    return get_environment().lower() == 'production'


def is_development() -> bool:
    """Check if running in development environment"""
    return get_environment().lower() == 'development'


def is_cloud_run() -> bool:
    """Check if running in Google Cloud Run"""
    return os.getenv('K_SERVICE') is not None


# Global configuration instance
_config_instance: Optional[GatewayConfig] = None


def get_config() -> GatewayConfig:
    """Get the global configuration instance"""
    global _config_instance
    
    if _config_instance is None:
        _config_instance = load_config()
    
    return _config_instance


def reload_config():
    """Reload the global configuration"""
    global _config_instance
    _config_instance = None
    return get_config()