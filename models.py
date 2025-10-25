```python
"""
This module defines the database models for the Todo application using SQLAlchemy.
It includes models for Todo items and Users, along with their relationships
and associated utility methods.
"""

import enum
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from werkzeug.security import generate_password_hash, check_password_hash

# Base class for declarative models
Base = declarative_base()

class TodoStatus(enum.Enum):
    """
    Represents the possible statuses for a Todo item.
    """
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class TimestampMixin:
    """
    A mixin to add `created_at` and `updated_at` timestamp columns
    to SQLAlchemy models.
    """
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class User(Base, TimestampMixin):
    """
    Represents a user in the Todo application.
    Each user has a unique username and email, and a hashed password.
    """
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(128), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False) # Increased length for modern password hashes

    # Relationship to Todo items
    # 'todos' is a collection of Todo objects associated with this user.
    # cascade="all, delete-orphan" means that if a User is deleted, all
    # associated Todo items will also be deleted. If a Todo is removed
    # from user.todos, it will be deleted from the database.
    todos = relationship(
        'Todo',
        back_populates='user',
        lazy='dynamic', # Use 'dynamic' for efficient querying of related items
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        """
        Provides a readable representation of a User object.
        """
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"

    @property
    def password(self):
        """
        Prevents direct reading of the password attribute.
        """
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        """
        Hashes the provided password and stores it in password_hash.
        """
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        """
        Verifies if the provided password matches the stored hash.
        """
        return check_password_hash(self.password_hash, password)

class Todo(Base, TimestampMixin):
    """
    Represents a single Todo item.
    Each Todo item belongs to a User.
    """
    __tablename__ = 'todos'

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(128), index=True, nullable=False) # Title is required
    description = Column(Text, nullable=True) # Use Text for potentially long descriptions
    status = Column(Enum(TodoStatus), default=TodoStatus.PENDING, nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False) # Explicit completion flag

    # Foreign key to the User model
    user_id = Column(Integer, ForeignKey('users.id'), index=True, nullable=False)

    # Relationship to the User model
    # 'user' is the User object that owns this Todo.
    user = relationship('User', back_populates='todos')

    def __repr__(self):
        """
        Provides a readable representation of a Todo object.
        """
        return (
            f"<Todo(id={self.id}, title='{self.title}', status='{self.status.value}', "
            f"user_id={self.user_id})>"
        )
```