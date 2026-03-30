import django_tables2 as tables
from django.utils.translation import gettext_lazy as _
from lot.models import Lot, Beneficiary
from django.utils.safestring import mark_safe

class LotTable(tables.Table):
    select = tables.CheckBoxColumn(
        accessor='id',
        attrs={
            'th__input': {
                'id': 'select-all',
                'class': 'form-check-input'
            },
            'td__input': {
                'class': 'select-checkbox form-check-input'
            },
        },
        orderable=False
    )
    name = tables.Column(
        linkify=("dashboard:lot", {"pk": tables.A("id")}),
        verbose_name=_("Lot Name"),
        attrs={
        }
    )
    description = tables.Column(
        verbose_name=_("Description"),
        default=_("No description"),
        attrs={
            'td': {'class': 'text-muted'}
        }
    )
    archived = tables.Column(
        verbose_name=_("Status"),
    )
    device_count = tables.Column(
        verbose_name=_("Devices"),
        accessor='device_count',
    )
    created = tables.DateColumn(
        format="Y-m-d",
        verbose_name=_("Created On"),
    )
    user = tables.Column(
        verbose_name=_("Created By"),
        default=_("Unknown"),
    )
    actions = tables.TemplateColumn(
        template_name="lot_actions.html",
        verbose_name=_(""),
        orderable=False
    )

    def render_archived(self, value):
        if value:
            return mark_safe('<span class="badge bg-warning"><i class="bi bi-archive-fill"></i></span>')
        return mark_safe('<span class="badge bg-success"><i class="bi bi-folder-fill"></i></span>')

    class Meta:
        template_name = "custom_table.html"
        model = Lot
        fields = ("select", "archived", "name", "description", "device_count", "created", "user", "actions")
        order_by = ("-created",)


class BeneficiaryTable(tables.Table):
    email = tables.Column(
        verbose_name=_("Beneficiary"),
        attrs={'td': {'class': 'font-monospace'}},
    )
    shop_email = tables.Column(
        accessor='shop__user__email',
        verbose_name=_("Shop"),
        attrs={'td': {'class': 'font-monospace'}},
        orderable=False,
    )
    sign_conditions = tables.Column(
        verbose_name=_("Accepted terms"),
        attrs={'td': {'class': 'font-monospace'}},
        orderable=True,
        default=None,
    )
    devices = tables.TemplateColumn(
        template_code=(
            '{% load i18n %}'
            '<a href="{% url \'lot:devices_beneficiary\' table.lot_id record.id %}">'
            '{% trans "Devices" %}</a>'
        ),
        verbose_name=_("Devices"),
        orderable=False,
    )
    web = tables.TemplateColumn(
        template_code=(
            '{% load i18n %}'
            '<a href="{% url \'lot:web_beneficiary\' table.lot_id record.id %}">'
            '{% trans "web" %}</a>'
        ),
        verbose_name=_("Web"),
        orderable=False,
    )
    assign = tables.TemplateColumn(
        template_code=(
            '{% load i18n %}'
            '<a href="{% url \'lot:add_device_beneficiary\' table.lot_id record.id %}"'
            '   class="btn btn-sm btn-outline-primary align-items-center">'
            '  <i class="bi bi-plus-circle me-1"></i>{% trans "Assign" %}'
            '</a>'
        ),
        verbose_name=_(""),
        orderable=False,
    )
    deallocate = tables.TemplateColumn(
        template_code=(
            '{% load i18n %}'
            '<button type="button" class="btn btn-sm btn-outline-danger d-flex align-items-center"'
            '        data-bs-toggle="modal" data-bs-target="#deleteModal{{ record.id }}">'
            '  <i class="bi bi-trash me-1"></i>{% trans "Deallocate" %}'
            '</button>'
            '<div class="modal fade" id="deleteModal{{ record.id }}" tabindex="-1" aria-hidden="true">'
            '  <div class="modal-dialog">'
            '    <div class="modal-content">'
            '      <div class="modal-header">'
            '        <h5 class="modal-title">{% trans "Deallocate Beneficiary" %}</h5>'
            '        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>'
            '      </div>'
            '      <div class="modal-body">'
            '        <p>{% trans "Are you sure you want to deallocate this beneficiary?" %}</p>'
            '      </div>'
            '      <div class="modal-footer">'
            '        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{% trans "Cancel" %}</button>'
            '        <a class="btn btn-danger" href="{% url \'lot:del_beneficiary\' table.lot_id record.id %}">{% trans "Deallocate" %}</a>'
            '      </div>'
            '    </div>'
            '  </div>'
            '</div>'
        ),
        verbose_name=_(""),
        orderable=False,
    )

    def render_sign_conditions(self, value):
        if value:
            return mark_safe(f'{value} <i class="bi bi-shield-check text-primary"></i>')
        return mark_safe('<i class="bi bi-shield-slash text-danger"></i>')

    class Meta:
        template_name = "custom_table.html"
        model = Beneficiary
        fields = ("email", "shop_email", "sign_conditions", "devices", "web", "assign", "deallocate")
        order_by = ("email",)
