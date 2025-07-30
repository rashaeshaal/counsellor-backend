from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from urllib.parse import parse_qs

@database_sync_to_async
def get_user_from_token(token):
    from django.contrib.auth.models import AnonymousUser
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        # Validate the JWT token
        access_token = AccessToken(token)
        user = User.objects.get(id=access_token['user_id'])
        return user
    except Exception:
        return AnonymousUser()

class QueryAuthTokenMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Extract token from query string
        query_string = scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        token = query_params.get('token', [None])[0]

        if token:
            # Authenticate user based on token
            scope['user'] = await get_user_from_token(token)
        else:
            scope['user'] = AnonymousUser()

        return await self.inner(scope, receive, send)