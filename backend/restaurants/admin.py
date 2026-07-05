from django.contrib.gis import admin

from .models import Restaurant, MenuItem

from django.contrib.gis.db import models
from django.contrib.gis.forms import OSMWidget
# OpenLayersWidget


class RestaurantAdmin(admin.ModelAdmin):
    formfield_overrides = {models.PointField: {"widget": OSMWidget}}


admin.site.register(Restaurant, RestaurantAdmin)
admin.site.register(MenuItem)
