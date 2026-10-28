"""
API Views for Todo domain
Implements REST endpoints for todos, categories, and tags
"""
import logging

from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError
from django.contrib.auth import get_user_model

from .models import Todo, Category, Tag
from .schemas import (
    TodoListSerializer,
    TodoDetailSerializer,
    TodoCreateSerializer,
    TodoUpdateSerializer,
    TodoToggleSerializer,
    TodoFilterSerializer,
    TodoStatsSerializer,
    BulkDeleteSerializer,
    BulkCompleteSerializer,
    CategorySerializer,
    CategoryCreateSerializer,
    TagSerializer,
    TagCreateSerializer,
)
from .services import TodoService, CategoryService, TagService
from ..core.permissions import IsTodoOwner, IsCategoryOwner, IsTagOwner

logger = logging.getLogger(__name__)
User = get_user_model()


class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination class."""
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class TodoListCreateView(APIView):
    """
    GET /api/todos/ - List todos with filtering
    POST /api/todos/ - Create a new todo
    """
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get(self, request):
        """List todos with filtering and pagination."""
        # Parse filter parameters
        filter_serializer = TodoFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        filters = filter_serializer.validated_data
        
        service = TodoService()
        todos = service.list_todos(
            user=request.user,
            is_completed=filters.get("is_completed"),
            priority=filters.get("priority"),
            category=filters.get("category"),
            tags=filters.get("tags"),
            due_before=filters.get("due_before"),
            due_after=filters.get("due_after"),
            search=filters.get("search"),
            ordering=filters.get("ordering", "-created_at"),
        )
        
        # Paginate results
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(todos, request)
        serializer = TodoListSerializer(page, many=True)
        
        return paginator.get_paginated_response(serializer.data)
    
    def post(self, request):
        """Create a new todo."""
        serializer = TodoCreateSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        
        service = TodoService()
        todo = service.create_todo(
            user=request.user,
            **serializer.validated_data
        )
        
        return Response(
            TodoDetailSerializer(todo).data,
            status=status.HTTP_201_CREATED
        )


class TodoDetailView(APIView):
    """
    GET /api/todos/{id}/ - Get todo details
    PUT /api/todos/{id}/ - Update todo
    PATCH /api/todos/{id}/ - Partial update todo
    DELETE /api/todos/{id}/ - Delete todo
    """
    permission_classes = [permissions.IsAuthenticated, IsTodoOwner]
    
    def get_object(self, pk, user):
        """Get todo and check ownership."""
        service = TodoService()
        todo = service.get_todo(pk, user)
        # Check object permission
        self.check_object_permissions(self.request, todo)
        return todo
    
    def get(self, request, pk):
        """Get todo details."""
        todo = self.get_object(pk, request.user)
        serializer = TodoDetailSerializer(todo)
        return Response(serializer.data)
    
    def put(self, request, pk):
        """Update todo."""
        todo = self.get_object(pk, request.user)
        serializer = TodoUpdateSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        
        service = TodoService()
        todo = service.update_todo(
            todo_id=pk,
            user=request.user,
            **serializer.validated_data
        )
        
        return Response(TodoDetailSerializer(todo).data)
    
    def patch(self, request, pk):
        """Partial update todo."""
        return self.put(request, pk)
    
    def delete(self, request, pk):
        """Delete todo."""
        todo = self.get_object(pk, request.user)
        service = TodoService()
        service.delete_todo(pk, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TodoToggleView(APIView):
    """
    POST /api/todos/{id}/toggle/ - Toggle todo completion status
    """
    permission_classes = [permissions.IsAuthenticated, IsTodoOwner]
    
    def get_object(self, pk, user):
        """Get todo and check ownership."""
        service = TodoService()
        todo = service.get_todo(pk, user)
        self.check_object_permissions(self.request, todo)
        return todo
    
    def post(self, request, pk):
        """Toggle todo completion."""
        self.get_object(pk, request.user)
        service = TodoService()
        todo = service.toggle_complete(pk, request.user)
        return Response(TodoDetailSerializer(todo).data)


class TodoBulkDeleteView(APIView):
    """
    POST /api/todos/bulk-delete/ - Bulk delete todos
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Bulk delete todos."""
        serializer = BulkDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = TodoService()
        count = service.bulk_delete(
            serializer.validated_data["ids"],
            request.user
        )
        
        return Response({
            "message": f"Deleted {count} todos",
            "deleted_count": count
        })


class TodoBulkCompleteView(APIView):
    """
    POST /api/todos/bulk-complete/ - Bulk mark todos as complete/incomplete
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Bulk complete todos."""
        serializer = BulkCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = TodoService()
        count = service.bulk_complete(
            serializer.validated_data["ids"],
            request.user,
            is_completed=serializer.validated_data.get("is_completed", True)
        )
        
        return Response({
            "message": f"Updated {count} todos",
            "updated_count": count
        })


class TodoStatsView(APIView):
    """
    GET /api/todos/stats/ - Get todo statistics
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get todo statistics."""
        service = TodoService()
        stats = service.get_statistics(request.user)
        serializer = TodoStatsSerializer(stats)
        return Response(serializer.data)


class TodoOverdueView(APIView):
    """
    GET /api/todos/overdue/ - Get overdue todos
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get overdue todos."""
        service = TodoService()
        todos = service.get_overdue_todos(request.user)
        serializer = TodoListSerializer(todos, many=True)
        return Response(serializer.data)


class TodoTodayView(APIView):
    """
    GET /api/todos/today/ - Get todos due today
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get todos due today."""
        service = TodoService()
        todos = service.get_todos_due_today(request.user)
        serializer = TodoListSerializer(todos, many=True)
        return Response(serializer.data)


class TodoWeekView(APIView):
    """
    GET /api/todos/week/ - Get todos due this week
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get todos due this week."""
        service = TodoService()
        todos = service.get_todos_due_this_week(request.user)
        serializer = TodoListSerializer(todos, many=True)
        return Response(serializer.data)


# Category Views

class CategoryListCreateView(APIView):
    """
    GET /api/categories/ - List categories
    POST /api/categories/ - Create a new category
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """List categories."""
        service = CategoryService()
        categories = service.list_categories(request.user)
        serializer = CategorySerializer(categories, many=True)
        return Response(serializer.data)
    
    def post(self, request):
        """Create a new category."""
        serializer = CategoryCreateSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        
        service = CategoryService()
        category = service.create_category(
            user=request.user,
            **serializer.validated_data
        )
        
        return Response(
            CategorySerializer(category).data,
            status=status.HTTP_201_CREATED
        )


class CategoryDetailView(APIView):
    """
    GET /api/categories/{id}/ - Get category details
    PUT /api/categories/{id}/ - Update category
    PATCH /api/categories/{id}/ - Partial update category
    DELETE /api/categories/{id}/ - Delete category
    """
    permission_classes = [permissions.IsAuthenticated, IsCategoryOwner]
    
    def get_object(self, pk, user):
        """Get category and check ownership."""
        service = CategoryService()
        category = service.get_category(pk, user)
        self.check_object_permissions(self.request, category)
        return category
    
    def get(self, request, pk):
        """Get category details."""
        category = self.get_object(pk, request.user)
        serializer = CategorySerializer(category)
        return Response(serializer.data)
    
    def put(self, request, pk):
        """Update category."""
        category = self.get_object(pk, request.user)
        serializer = CategoryCreateSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        
        service = CategoryService()
        category = service.update_category(
            category_id=pk,
            user=request.user,
            **serializer.validated_data
        )
        
        return Response(CategorySerializer(category).data)
    
    def patch(self, request, pk):
        """Partial update category."""
        return self.put(request, pk)
    
    def delete(self, request, pk):
        """Delete category."""
        category = self.get_object(pk, request.user)
        service = CategoryService()
        service.delete_category(pk, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# Tag Views

class TagListCreateView(APIView):
    """
    GET /api/tags/ - List tags
    POST /api/tags/ - Create a new tag
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """List tags."""
        service = TagService()
        tags = service.list_tags(request.user)
        serializer = TagSerializer(tags, many=True)
        return Response(serializer.data)
    
    def post(self, request):
        """Create a new tag."""
        serializer = TagCreateSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        
        service = TagService()
        tag = service.create_tag(
            user=request.user,
            **serializer.validated_data
        )
        
        return Response(
            TagSerializer(tag).data,
            status=status.HTTP_201_CREATED
        )


class TagDetailView(APIView):
    """
    GET /api/tags/{id}/ - Get tag details
    PUT /api/tags/{id}/ - Update tag
    PATCH /api/tags/{id}/ - Partial update tag
    DELETE /api/tags/{id}/ - Delete tag
    """
    permission_classes = [permissions.IsAuthenticated, IsTagOwner]
    
    def get_object(self, pk, user):
        """Get tag and check ownership."""
        service = TagService()
        tag = service.get_tag(pk, user)
        self.check_object_permissions(self.request, tag)
        return tag
    
    def get(self, request, pk):
        """Get tag details."""
        tag = self.get_object(pk, request.user)
        serializer = TagSerializer(tag)
        return Response(serializer.data)
    
    def put(self, request, pk):
        """Update tag."""
        tag = self.get_object(pk, request.user)
        serializer = TagCreateSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        
        service = TagService()
        tag = service.update_tag(
            tag_id=pk,
            user=request.user,
            **serializer.validated_data
        )
        
        return Response(TagSerializer(tag).data)
    
    def patch(self, request, pk):
        """Partial update tag."""
        return self.put(request, pk)
    
    def delete(self, request, pk):
        """Delete tag."""
        tag = self.get_object(pk, request.user)
        service = TagService()
        service.delete_tag(pk, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


__all__ = [
    "TodoListCreateView",
    "TodoDetailView",
    "TodoToggleView",
    "TodoBulkDeleteView",
    "TodoBulkCompleteView",
    "TodoStatsView",
    "TodoOverdueView",
    "TodoTodayView",
    "TodoWeekView",
    "CategoryListCreateView",
    "CategoryDetailView",
    "TagListCreateView",
    "TagDetailView",
]
