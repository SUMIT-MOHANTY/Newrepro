"""
Migration to create Todo, Category, and Tag tables
"""
import uuid
from datetime import datetime


def upgrade():
    """Create todo tables."""
    from django.db import connection
    
    with connection.cursor() as cursor:
        # Create categories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(100) NOT NULL,
                description TEXT,
                color VARCHAR(7) DEFAULT '#3B82F6',
                user_id UUID NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                CONSTRAINT unique_category_name_per_user UNIQUE (user_id, name)
            )
        """)
        
        # Create tags table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(50) NOT NULL,
                color VARCHAR(7) DEFAULT '#6B7280',
                user_id UUID NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                CONSTRAINT unique_tag_name_per_user UNIQUE (user_id, name)
            )
        """)
        
        # Create todos table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title VARCHAR(255) NOT NULL,
                description TEXT,
                is_completed BOOLEAN DEFAULT FALSE,
                priority VARCHAR(10) DEFAULT 'medium',
                due_date DATE,
                due_time TIME,
                category_id UUID,
                user_id UUID NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                completed_at TIMESTAMP WITH TIME ZONE
            )
        """)
        
        # Create todo_tags many-to-many table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS todo_tags (
                id SERIAL PRIMARY KEY,
                todo_id UUID NOT NULL,
                tag_id UUID NOT NULL,
                CONSTRAINT unique_todo_tag UNIQUE (todo_id, tag_id)
            )
        """)
        
        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_categories_user ON categories(user_id);
            CREATE INDEX IF NOT EXISTS idx_categories_user_name ON categories(user_id, name);
            CREATE INDEX IF NOT EXISTS idx_tags_user ON tags(user_id);
            CREATE INDEX IF NOT EXISTS idx_tags_user_name ON tags(user_id, name);
            CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(user_id);
            CREATE INDEX IF NOT EXISTS idx_todos_user_completed ON todos(user_id, is_completed);
            CREATE INDEX IF NOT EXISTS idx_todos_user_priority ON todos(user_id, priority);
            CREATE INDEX IF NOT EXISTS idx_todos_user_due_date ON todos(user_id, due_date);
            CREATE INDEX IF NOT EXISTS idx_todos_user_category ON todos(user_id, category_id);
            CREATE INDEX IF NOT EXISTS idx_todos_user_created ON todos(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_todos_due_completed ON todos(due_date, is_completed);
            CREATE INDEX IF NOT EXISTS idx_todo_tags_todo ON todo_tags(todo_id);
            CREATE INDEX IF NOT EXISTS idx_todo_tags_tag ON todo_tags(tag_id);
        """)
        
        print("Todo tables created successfully")


def downgrade():
    """Drop todo tables."""
    from django.db import connection
    
    with connection.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS todo_tags CASCADE")
        cursor.execute("DROP TABLE IF EXISTS todos CASCADE")
        cursor.execute("DROP TABLE IF EXISTS tags CASCADE")
        cursor.execute("DROP TABLE IF EXISTS categories CASCADE")
        print("Todo tables dropped successfully")


if __name__ == "__main__":
    upgrade()
