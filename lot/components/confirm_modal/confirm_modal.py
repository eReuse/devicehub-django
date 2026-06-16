from typing import Any, Dict, Optional

from django_components import Component, register


@register("confirm_modal")
class ConfirmModal(Component):
    template_name = "confirm_modal/confirm_modal.html"

    def get_context_data(
        self,
        modal_id: str,
        modal_title: str,
        action_text: str,
        action_url: Optional[str] = None,
        action_form_url: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return {
            "modal_id": modal_id,
            "modal_title": modal_title,
            "action_text": action_text,
            "action_url": action_url,
            "action_form_url": action_form_url,
        }
