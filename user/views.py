from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from dashboard.mixins import DashboardView



class ProfileView(DashboardView):
    template_name = "profile.html"
    subtitle = _('My personal data')
    icon = 'bi bi-person-gear'
    fields = ('first_name', 'last_name', 'email')
    success_url = reverse_lazy('idhub:user_profile')
    model = User

    def get_queryset(self, **kwargs):
        queryset = Membership.objects.select_related('user').filter(
                user=self.request.user)

        return queryset

    def get_object(self):
        return self.request.user

    def get_form(self):
        form = super().get_form()
        return form

    def form_valid(self, form):
        return super().form_valid(form)
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'lang': self.request.LANGUAGE_CODE,
        })
        return context

