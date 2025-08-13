"""
SQLAlchemy database models for tenant-aware authentication and authorization.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from enum import Enum

from sqlalchemy import (
    String, Text, Integer, DateTime, Boolean, JSON, ForeignKey, 
    Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class TenantStatus(str, Enum):
    """Tenant status enumeration."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class UserStatus(str, Enum):
    """User status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class APIKeyStatus(str, Enum):
    """API key status enumeration."""
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class Environment(str, Enum):
    """Environment enumeration for API keys."""
    PRODUCTION = "prod"
    STAGING = "staging"
    DEVELOPMENT = "dev"
    TEST = "test"


class Permission(str, Enum):
    """Permission enumeration for RBAC."""
    # Agent operations
    AGENT_READ = "agent:read"
    AGENT_WRITE = "agent:write"
    AGENT_DELETE = "agent:delete"
    AGENT_EXECUTE = "agent:execute"
    
    # Workflow operations
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_WRITE = "workflow:write"
    WORKFLOW_DELETE = "workflow:delete"
    WORKFLOW_EXECUTE = "workflow:execute"
    
    # Resource operations
    RESOURCE_READ = "resource:read"
    RESOURCE_WRITE = "resource:write"
    RESOURCE_DELETE = "resource:delete"
    
    # Tool operations
    TOOL_READ = "tool:read"
    TOOL_WRITE = "tool:write"
    TOOL_DELETE = "tool:delete"
    TOOL_EXECUTE = "tool:execute"
    
    # Admin operations
    TENANT_ADMIN = "tenant:admin"
    USER_ADMIN = "user:admin"
    API_KEY_ADMIN = "api_key:admin"
    AUDIT_READ = "audit:read"


class Tenant(Base):
    """Tenant model for multi-tenancy support."""
    __tablename__ = "tenants"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Status and lifecycle
    status: Mapped[TenantStatus] = mapped_column(
        String(20), 
        nullable=False, 
        default=TenantStatus.ACTIVE
    )
    
    # Rate limiting configuration
    rate_limit_per_hour: Mapped[int] = mapped_column(Integer, default=1000)
    rate_limit_per_day: Mapped[int] = mapped_column(Integer, default=10000)
    
    # Billing and plan information
    plan: Mapped[str] = mapped_column(String(50), default="free")
    
    # Metadata
    settings: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User", 
        back_populates="tenant",
        cascade="all, delete-orphan"
    )
    api_keys: Mapped[List["APIKey"]] = relationship(
        "APIKey",
        back_populates="tenant",
        cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="tenant",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_tenant_slug", "slug"),
        Index("idx_tenant_status", "status"),
        Index("idx_tenant_created_at", "created_at"),
        CheckConstraint(
            "rate_limit_per_hour > 0 AND rate_limit_per_day > 0",
            name="check_positive_rate_limits"
        ),
    )
    
    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name='{self.name}', slug='{self.slug}')>"


class User(Base):
    """User model with tenant association."""
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # User details
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(100))
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Authentication
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    is_service_account: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Status and settings
    status: Mapped[UserStatus] = mapped_column(
        String(20),
        nullable=False,
        default=UserStatus.ACTIVE
    )
    is_tenant_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Last activity tracking
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
    api_keys: Mapped[List["APIKey"]] = relationship(
        "APIKey",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    roles: Mapped[List["UserRole"]] = relationship(
        "UserRole",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_tenant_email"),
        UniqueConstraint("tenant_id", "username", name="uq_tenant_username"),
        Index("idx_user_email", "email"),
        Index("idx_user_tenant_id", "tenant_id"),
        Index("idx_user_status", "status"),
        Index("idx_user_last_activity", "last_activity_at"),
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', tenant_id={self.tenant_id})>"


class Role(Base):
    """Role model for RBAC."""
    __tablename__ = "roles"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Role details
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Permissions as JSON array
    permissions: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    
    # System roles cannot be modified/deleted
    is_system_role: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    user_roles: Mapped[List["UserRole"]] = relationship(
        "UserRole",
        back_populates="role",
        cascade="all, delete-orphan"
    )
    
    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_role_name"),
        Index("idx_role_tenant_id", "tenant_id"),
        Index("idx_role_name", "name"),
    )
    
    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name='{self.name}', tenant_id={self.tenant_id})>"


class UserRole(Base):
    """User-Role association model."""
    __tablename__ = "user_roles"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    granted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id")
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="roles")
    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")
    granted_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[granted_by]
    )
    
    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        Index("idx_user_role_user_id", "user_id"),
        Index("idx_user_role_role_id", "role_id"),
    )
    
    def __repr__(self) -> str:
        return f"<UserRole(user_id={self.user_id}, role_id={self.role_id})>"


class APIKey(Base):
    """API key model with tenant-aware format."""
    __tablename__ = "api_keys"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # API key details
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Key format: mesh_<tenant_id>_<environment>_<key>
    key_prefix: Mapped[str] = mapped_column(String(50), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    environment: Mapped[Environment] = mapped_column(
        String(20),
        nullable=False,
        default=Environment.DEVELOPMENT
    )
    
    # Status and permissions
    status: Mapped[APIKeyStatus] = mapped_column(
        String(20),
        nullable=False,
        default=APIKeyStatus.ACTIVE
    )
    
    # Rate limiting (overrides tenant defaults if set)
    rate_limit_per_hour: Mapped[Optional[int]] = mapped_column(Integer)
    rate_limit_per_day: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Permissions and scopes
    permissions: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    scopes: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    
    # IP allowlist for additional security
    allowed_ips: Mapped[Optional[List[str]]] = mapped_column(JSON)
    
    # Expiration
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Usage tracking
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id")
    )
    
    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="api_keys")
    user: Mapped["User"] = relationship("User", back_populates="api_keys")
    revoked_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[revoked_by]
    )
    
    # Indexes and constraints
    __table_args__ = (
        Index("idx_api_key_hash", "key_hash"),
        Index("idx_api_key_tenant_id", "tenant_id"),
        Index("idx_api_key_user_id", "user_id"),
        Index("idx_api_key_status", "status"),
        Index("idx_api_key_environment", "environment"),
        Index("idx_api_key_expires_at", "expires_at"),
        Index("idx_api_key_last_used", "last_used_at"),
        CheckConstraint(
            "rate_limit_per_hour IS NULL OR rate_limit_per_hour > 0",
            name="check_positive_hour_rate_limit"
        ),
        CheckConstraint(
            "rate_limit_per_day IS NULL OR rate_limit_per_day > 0",
            name="check_positive_day_rate_limit"
        ),
    )
    
    def __repr__(self) -> str:
        return f"<APIKey(id={self.id}, name='{self.name}', tenant_id={self.tenant_id})>"


class AuditLog(Base):
    """Audit log model for tracking authentication and authorization events."""
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )
    
    # Event details
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_category: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource: Mapped[Optional[str]] = mapped_column(String(255))
    resource_id: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Request details
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))  # IPv6 support
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    request_id: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Authentication method
    auth_method: Mapped[Optional[str]] = mapped_column(String(50))
    api_key_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL")
    )
    
    # Result and metadata
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(100))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    metadata: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Timestamps
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="audit_logs")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")
    api_key: Mapped[Optional["APIKey"]] = relationship("APIKey")
    
    # Indexes and constraints
    __table_args__ = (
        Index("idx_audit_log_tenant_id", "tenant_id"),
        Index("idx_audit_log_user_id", "user_id"),
        Index("idx_audit_log_timestamp", "timestamp"),
        Index("idx_audit_log_event_type", "event_type"),
        Index("idx_audit_log_event_category", "event_category"),
        Index("idx_audit_log_success", "success"),
        Index("idx_audit_log_ip_address", "ip_address"),
        Index("idx_audit_log_api_key_id", "api_key_id"),
    )
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, event_type='{self.event_type}', tenant_id={self.tenant_id})>"