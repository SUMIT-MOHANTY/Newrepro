"""
Todo Router - REST API Endpoints for Todo Domain
Implements CRUD operations, filtering, pagination, bulk operations with DRF Spectacular OpenAPI documentation
"""
import logging
from uuid import UUID
from typing import List, Optional

from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiExample,
    OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes
from django.contrib.auth import get_user_model

from app.todos.models import Todo, Category, Tag
from app.schemas.todo import (
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
from app.services.todo_service import TodoService, CategoryService, TagService
from app.core.permissions import IsTodoOwner, IsCategoryOwner, IsTagOwner

logger = logging.getLogger(__name__)
User = get_user_model()


class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination class for todo endpoints."""
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema_view(
    get=extend_schema(
        summary="List todos",
        description="Get a paginated list of todos with optional filtering by status, priority, category, and search.",
        parameters=[
            OpenApiParameter(
                name="is_completed",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="Filter by completion status",
                required=False,
            ),
            OpenApiParameter(
                name="priority",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Filter by priority (low, medium, high, urgent)",
                required=False,
            ),
            OpenApiParameter(
                name="category",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                description="Filter by category ID",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Search in title and description",
                required=False,
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Order by field (created_at, -created_at, due_date, -due_date, priority, -priority, title, -title)",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Page number",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Number of items per page (max 100)",
                required=False,
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=TodoListSerializer(many=True),
                description="Paginated list of todos",
            ),
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Todos"],
    ),
    post=extend_schema(
        summary="Create todo",
        description="Create a new todo item.",
        request=TodoCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=TodoDetailSerializer,
                description="Todo created successfully",
            ),
            400: OpenApiResponse(description="Invalid input data"),
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Todos"],
    ),
)
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


@extend_schema_view(
    get=extend_schema(
        summary="Get todo details",
        description="Retrieve detailed information about a specific todo.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Todo ID",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=TodoDetailSerializer,
                description="Todo details",
            ),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - not the owner"),
            404: OpenApiResponse(description="Todo not found"),
        },
        tags=["Todos"],
    ),
    put=extend_schema(
        summary="Update todo",
        description="Update all fields of a todo.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Todo ID",
            ),
        ],
        request=TodoUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=TodoDetailSerializer,
                description="Todo updated successfully",
            ),
            400: OpenApiResponse(description="Invalid input data"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - not the owner"),
            404: OpenApiResponse(description="Todo not found"),
        },
        tags=["Todos"],
    ),
    patch=extend_schema(
        summary="Partial update todo",
        description="Update specific fields of a todo.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Todo ID",
            ),
        ],
        request=TodoUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=TodoDetailSerializer,
                description="Todo updated successfully",
            ),
            400: OpenApiResponse(description="Invalid input data"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - not the owner"),
            404: OpenApiResponse(description="Todo not found"),
        },
        tags=["Todos"],
    ),
    delete=extend_schema(
        summary="Delete todo",
        description="Delete a todo permanently.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Todo ID",
            ),
        ],
        responses={
            204: OpenApiResponse(description="Todo deleted successfully"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - not the owner"),
            404: OpenApiResponse(description="Todo not found"),
        },
        tags=["Todos"],
    ),
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


@extend_schema_view(
    post=extend_schema(
        summary="Toggle todo completion",
        description="Toggle the completion status of a todo.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Todo ID",
            ),
        ],
        request=TodoToggleSerializer,
        responses={
            200: OpenApiResponse(
                response=TodoDetailSerializer,
                description="Todo toggled successfully",
            ),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - not the owner"),
            404: OpenApiResponse(description="Todo not found"),
        },
        tags=["Todos"],
    ),
)
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


@extend_schema_view(
    post=extend_schema(
        summary="Bulk delete todos",
        description="Delete multiple todos at once. Only todos owned by the current user will be deleted.",
        request=BulkDeleteSerializer,
        responses={
            200: OpenApiResponse(
                response={"type": "object", "properties": {
                    "message": {"type": "string"},
                    "deleted_count": {"type": "integer"}
                }},
                description="Todos deleted successfully",
            ),
            400: OpenApiResponse(description="Invalid input data"),
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Todos"],
    ),
)
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


@extend_schema_view(
    post=extend_schema(
        summary="Bulk complete todos",
        description="Mark multiple todos as complete or incomplete. Only todos owned by the current user will be updated.",
        request=BulkCompleteSerializer,
        responses={
            200: OpenApiResponse(
                response={"type": "object", "properties": {
                    "message": {"type": "string"},
                    "updated_count": {"type": "integer"}
                }},
                description="Todos updated successfully",
            ),
            400: OpenApiResponse(description="Invalid input data"),
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Todos"],
    ),
)
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


@extend_schema_view(
    get=extend_schema(
        summary="Get todo statistics",
        description="Get statistics about todos including counts by priority and category.",
        responses={
            200: OpenApiResponse(
                response=TodoStatsSerializer,
                description="Todo statistics",
            ),
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Todos"],
    ),
)
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


@extend_schema_view(
    get=extend_schema(
        summary="Get overdue todos",
        description="Get all todos that are past their due date and not completed.",
        responses={
            200: OpenApiResponse(
                response=TodoListSerializer(many=True),
                description="List of overdue todos",
            ),
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Todos"],
    ),
)
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


@extend_schema_view(
    get=extend_schema(
        summary="Get todos due today",
        description="Get all todos that are due today and not completed.",
        responses={
            200: OpenApiResponse(
                response=TodoListSerializer(many=True),
                description="List of todos due today",
            ),
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Todos"],
    ),
)
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


@extend_schema_view(
    get=extend_schema(
        summary="Get todos due this week",
        description="Get all todos that are due within the next 7 days and not completed.",
        responses={
            200: OpenApiResponse(
                response=TodoListSerializer(many=True),
                description="List of todos due this week",
            ),
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Todos"],
    ),
)
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

@extend_schema_view(
    get=extend_schema(
        summary="List categories",
        description="Get all categories for the current user.",
        responses={
            200: OpenApiResponse(
                response=CategorySerializer(many=True),
                description="List of categories",
            ),
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Categories"],
    ),
    post=extend_schema(
        summary="Create category",
        description="Create a new category.",
        request=CategoryCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=CategorySerializer,
                description="Category created successfully",
            ),
            400: OpenApiResponse(description="Invalid input data"),
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Categories"],
    ),
)
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


@extend_schema_view(
    get=extend_schema(
        summary="Get category details",
        description="Retrieve detailed information about a specific category.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Category ID",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=CategorySerializer,
                description="Category details",
            ),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - not the owner"),
            404: OpenApiResponse(description="Category not found"),
        },
        tags=["Categories"],
    ),
    put=extend_schema(
        summary="Update category",
        description="Update a category.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Category ID",
            ),
        ],
        request=CategoryCreateSerializer,
        responses={
            200: OpenApiResponse(
                response=CategorySerializer,
                description="Category updated successfully",
            ),
            400: OpenApiResponse(description="Invalid input data"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - not the owner"),
            404: OpenApiResponse(description="Category not found"),
        },
        tags=["Categories"],
    ),
    patch=extend_schema(
        summary="Partial update category",
        description="Update specific fields of a category.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Category ID",
            ),
        ],
        request=CategoryCreateSerializer,
        responses={
            200: OpenApiResponse(
                response=CategorySerializer,
                description="Category updated successfully",
            ),
            400: OpenApiResponse(description="Invalid input data"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - not the owner"),
            404: OpenApiResponse(description="Category not found"),
        },
        tags=["Categories"],
    ),
    delete=extend_schema(
        summary="Delete category",
        description="Delete a category. Todos in this category will have their category set to null.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Category ID",
            ),
        ],
        responses={
            204: OpenApiResponse(description="Category deleted successfully"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - not the owner"),
            404: OpenApiResponse(description="Category not found"),
        },
        tags=["Categories"],
    ),
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

@extend_schema_view(
    get=extend_schema(
        summary="List tags",
        description="Get all tags for the current user.",
        responses={
            200: OpenApiResponse(
                response=TagSerializer(many=True),
                description="List of tags",
            ),
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Tags"],
    ),
    post=extend_schema(
        summary="Create tag",
        description="Create a new tag.",
        request=TagCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=TagSerializer,
                description="Tag created successfully",
            ),
            400: OpenApiResponse(description="Invalid input data"),
            401: OpenApiResponse(description="Authentication required"),
        },
        tags=["Tags"],
    ),
)
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


@extend_schema_view(
    get=extend_schema(
        summary="Get tag details",
        description="Retrieve detailed information about a specific tag.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Tag ID",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=TagSerializer,
                description="Tag details",
            ),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - not the owner"),
            404: OpenApiResponse(description="Tag not found"),
        },
        tags=["Tags"],
    ),
    put=extend_schema(
        summary="Update tag",
        description="Update a tag.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Tag ID",
            ),
        ],
        request=TagCreateSerializer,
        responses={
            200: OpenApiResponse(
                response=TagSerializer,
                description="Tag updated successfully",
            ),
            400: OpenApiResponse(description="Invalid input data"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - not the owner"),
            404: OpenApiResponse(description="Tag not found"),
        },
        tags=["Tags"],
    ),
    patch=extend_schema(
        summary="Partial update tag",
        description="Update specific fields of a tag.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Tag ID",
            ),
        ],
        request=TagCreateSerializer,
        responses={
            200: OpenApiResponse(
                response=TagSerializer,
                description="Tag updated successfully",
            ),
            400: OpenApiResponse(description="Invalid input data"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - not the owner"),
            404: OpenApiResponse(description="Tag not found"),
        },
        tags=["Tags"],
    ),
    delete=extend_schema(
        summary="Delete tag",
        description="Delete a tag. The tag will be removed from all associated todos.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="Tag ID",
            ),
        ],
        responses={
            204: OpenApiResponse(description="Tag deleted successfully"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - not the owner"),
            404: OpenApiResponse(description="Tag not found"),
        },
        tags=["Tags"],
    ),
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
