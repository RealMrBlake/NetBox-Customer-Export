from netbox.plugins import PluginMenuButton, PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:netbox_customer_export:select",
        link_text="Kundendokumentation",
        permissions=["dcim.view_site"],
    ),
    PluginMenuItem(
        link="plugins:netbox_customer_export:symbol_list",
        link_text="Topologie-Symbole",
        permissions=["netbox_customer_export.view_topologysymbol"],
        buttons=(
            PluginMenuButton(
                link="plugins:netbox_customer_export:symbol_add",
                title="Hinzufügen",
                icon_class="mdi mdi-plus-thick",
                permissions=["netbox_customer_export.add_topologysymbol"],
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:netbox_customer_export:branding_list",
        link_text="Branding-Profile",
        permissions=["netbox_customer_export.view_brandingprofile"],
        buttons=(
            PluginMenuButton(
                link="plugins:netbox_customer_export:branding_add",
                title="Hinzufügen",
                icon_class="mdi mdi-plus-thick",
                permissions=["netbox_customer_export.add_brandingprofile"],
            ),
        ),
    ),
)
