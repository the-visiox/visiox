from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    scope = 'login'


class RegisterRateThrottle(AnonRateThrottle):
    scope = 'register'


class TokenRefreshRateThrottle(AnonRateThrottle):
    scope = 'token_refresh'
