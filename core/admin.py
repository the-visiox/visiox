from django.contrib import admin

from core.models import UserModel

# Register your models here.

class UserAdmin(admin.ModelAdmin):
    pass

admin.site.register(UserModel, UserAdmin)