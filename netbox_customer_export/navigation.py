from netbox.plugins import PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:netbox_customer_export:select",
        link_text="Kundendokumentation",
        permissions=["dcim.view_site"],
    ),
)
