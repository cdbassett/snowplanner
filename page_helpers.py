"""Small UI helpers shared by the region and area pages."""
from nicegui import ui
from icecream import ic


def make_class_toggler(search_class, add_class):
    search_class = "." + search_class
    def toggler(e):
        ic("toggle", e.value, search_class, add_class)
        if e.value: # e.value is True if checked, False if unchecked
            ui.query(search_class).classes(remove=add_class)
        else:
            ui.query(search_class).classes(add=add_class)

    return toggler


def make_visibility_toggler(search_class):
    return make_class_toggler(search_class, "hide-me")
