# serializers.py
from rest_framework import serializers
from .models import Problem, UserProblem, UserProfile

class ProblemSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True)  # Handle image field
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)  # Optional: Keep read-only for security

    class Meta:
        model = Problem
        fields = ['id', 'title', 'description', 'image', 'created_at', 'updated_at', 'created_by']

    def to_representation(self, instance):
        # Convert image to absolute URL
        representation = super().to_representation(instance)
        if instance.image:
            representation['image'] = instance.image.url
        return representation
class UserProblemSerializer(serializers.ModelSerializer):
    problem = ProblemSerializer(read_only=True)
    problem_id = serializers.PrimaryKeyRelatedField(
        queryset=Problem.objects.all(), source='problem', write_only=True
    )

    class Meta:
        model = UserProblem
        fields = ['id', 'user_profile', 'problem', 'problem_id', 'selected_at']
        read_only_fields = ['selected_at']