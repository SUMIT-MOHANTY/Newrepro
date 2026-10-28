"""
Pydantic-style schemas for Todo serialization
Used with Django REST Framework serializers
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model

from app.todos.models import Todo, Category, Tag

User = get_user_model()


class UserSummarySerializer(serializers.ModelSerializer):
    """Summary serializer for User - nested in Todo responses."""
    
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name"]
        read_only_fields = ["id"]


class TagSerializer(serializers.ModelSerializer):
    """Serializer for Tag model."""
    
    class Meta:
        model = Tag
        fields = ["id", "name", "color", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class TagCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating tags."""
    
    class Meta:
        model = Tag
        fields = ["name", "color"]
    
    def validate_name(self, value):
        """Ensure tag name is not empty and unique for user."""
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Tag name cannot be empty")
        
        user = self.context.get("request").user if self.context.get("request") else None
        if user and Tag.objects.filter(user=user, name__iexact=value).exists():
            if not self.instance or self.instance.name.lower() != value.lower():
                raise serializers.ValidationError("Tag with this name already exists")
        
        return value


class CategorySerializer(serializers.ModelSerializer):
    """Serializer for Category model."""
    todo_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ["id", "name", "description", "color", "todo_count", "created_at", "updated_at"]
        read_only_fields = ["id", "todo_count", "created_at", "updated_at"]
    
    def get_todo_count(self, obj):
        """Get the number of todos in this category."""
        return obj.todos.filter(is_completed=False).count()


class CategoryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating categories."""
    
    class Meta:
        model = Category
        fields = ["name", "description", "color"]
    
    def validate_name(self, value):
        """Ensure category name is not empty and unique for user."""
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Category name cannot be empty")
        
        user = self.context.get("request").user if self.context.get("request") else None
        if user and Category.objects.filter(user=user, name__iexact=value).exists():
            if not self.instance or self.instance.name.lower() != value.lower():
                raise serializers.ValidationError("Category with this name already exists")
        
        return value


class TodoListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for todo list views."""
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_color = serializers.CharField(source="category.color", read_only=True)
    tag_names = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Todo
        fields = [
            "id",
            "title",
            "is_completed",
            "priority",
            "due_date",
            "due_time",
            "category",
            "category_name",
            "category_color",
            "tag_names",
            "is_overdue",
            "created_at",
            "updated_at",
            "completed_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "completed_at"]
    
    def get_tag_names(self, obj):
        """Get list of tag names."""
        return [tag.name for tag in obj.tags.all()]


class TodoDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for todo views."""
    category_detail = CategorySerializer(source="category", read_only=True)
    tags_detail = TagSerializer(source="tags", many=True, read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    user = UserSummarySerializer(read_only=True)
    
    class Meta:
        model = Todo
        fields = [
            "id",
            "title",
            "description",
            "is_completed",
            "priority",
            "due_date",
            "due_time",
            "category",
            "category_detail",
            "tags",
            "tags_detail",
            "user",
            "is_overdue",
            "sort_order",
            "created_at",
            "updated_at",
            "completed_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "completed_at", "is_overdue", "user"]


class TodoCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating todos."""
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        allow_empty=True,
    )
    
    class Meta:
        model = Todo
        fields = [
            "title",
            "description",
            "priority",
            "due_date",
            "due_time",
            "category",
            "tag_ids",
            "sort_order",
        ]
    
    def validate_title(self, value):
        """Ensure title is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("Title cannot be empty")
        return value.strip()
    
    def validate_tag_ids(self, value):
        """Validate that tag IDs belong to the current user."""
        if not value:
            return value
        
        user = self.context.get("request").user if self.context.get("request") else None
        if user:
            user_tag_ids = set(Tag.objects.filter(user=user).values_list("id", flat=True))
            invalid_ids = set(str(v) for v in value) - set(str(v) for v in user_tag_ids)
            if invalid_ids:
                raise serializers.ValidationError(f"Invalid tag IDs: {invalid_ids}")
        
        return value
    
    def create(self, validated_data):
        """Create todo with tags."""
        tag_ids = validated_data.pop("tag_ids", [])
        todo = Todo.objects.create(**validated_data)
        
        if tag_ids:
            tags = Tag.objects.filter(id__in=tag_ids, user=todo.user)
            todo.tags.set(tags)
        
        return todo


class TodoUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating todos."""
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        allow_empty=True,
    )
    
    class Meta:
        model = Todo
        fields = [
            "title",
            "description",
            "is_completed",
            "priority",
            "due_date",
            "due_time",
            "category",
            "tag_ids",
            "sort_order",
        ]
    
    def validate_title(self, value):
        """Ensure title is not empty if provided."""
        if value is not None and not value.strip():
            raise serializers.ValidationError("Title cannot be empty")
        return value.strip() if value else value
    
    def validate_tag_ids(self, value):
        """Validate that tag IDs belong to the current user."""
        if not value:
            return value
        
        user = self.context.get("request").user if self.context.get("request") else None
        if user:
            user_tag_ids = set(Tag.objects.filter(user=user).values_list("id", flat=True))
            invalid_ids = set(str(v) for v in value) - set(str(v) for v in user_tag_ids)
            if invalid_ids:
                raise serializers.ValidationError(f"Invalid tag IDs: {invalid_ids}")
        
        return value
    
    def update(self, instance, validated_data):
        """Update todo with tags."""
        tag_ids = validated_data.pop("tag_ids", None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        
        if tag_ids is not None:
            tags = Tag.objects.filter(id__in=tag_ids, user=instance.user)
            instance.tags.set(tags)
        
        return instance


class TodoToggleSerializer(serializers.Serializer):
    """Serializer for toggle completion endpoint."""
    is_completed = serializers.BooleanField(required=False)


class BulkDeleteSerializer(serializers.Serializer):
    """Serializer for bulk delete operation."""
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=True,
        min_length=1,
    )


class BulkCompleteSerializer(serializers.Serializer):
    """Serializer for bulk complete operation."""
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=True,
        min_length=1,
    )
    is_completed = serializers.BooleanField(default=True)


class TodoFilterSerializer(serializers.Serializer):
    """Serializer for filtering todos."""
    is_completed = serializers.BooleanField(required=False)
    priority = serializers.ChoiceField(
        choices=[
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("urgent", "Urgent"),
        ],
        required=False,
    )
    category = serializers.UUIDField(required=False)
    tags = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
    )
    due_before = serializers.DateField(required=False)
    due_after = serializers.DateField(required=False)
    search = serializers.CharField(required=False, max_length=255)
    ordering = serializers.ChoiceField(
        choices=[
            "created_at",
            "-created_at",
            "due_date",
            "-due_date",
            "priority",
            "-priority",
            "title",
            "-title",
        ],
        required=False,
        default="-created_at",
    )


class TodoStatsSerializer(serializers.Serializer):
    """Serializer for todo statistics."""
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    pending = serializers.IntegerField()
    overdue = serializers.IntegerField()
    by_priority = serializers.DictField()
    by_category = serializers.DictField()


__all__ = [
    "UserSummarySerializer",
    "TagSerializer",
    "TagCreateSerializer",
    "CategorySerializer",
    "CategoryCreateSerializer",
    "TodoListSerializer",
    "TodoDetailSerializer",
    "TodoCreateSerializer",
    "TodoUpdateSerializer",
    "TodoToggleSerializer",
    "BulkDeleteSerializer",
    "BulkCompleteSerializer",
    "TodoFilterSerializer",
    "TodoStatsSerializer",
]
