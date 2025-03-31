import logging

from django.conf import settings
from django.template import loader
from django.core.mail import EmailMultiAlternatives
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site


logger = logging.getLogger(__name__)


class NotifyEmail:
    email_template_subject = ''
    email_template = ''
    email_template_html = ''

    def get_email_context(self, user):
        protocol = 'https' if self.request.is_secure() else 'http'
        current_site = get_current_site(self.request)
        site_name = current_site.name
        domain = current_site.domain

        context = {
            'email': user.email,
            'domain': domain,
            'site_name': site_name,
            'user': user,
            'protocol': protocol,
        }
        return context

    def send_email(self, user, token=None):
        """
        Send a email when a user is activated.
        """
        context = self.get_email_context(user, token)
        subject = loader.render_to_string(self.email_template_subject, context)
        # Email subject *must not* contain newlines
        subject = ''.join(subject.splitlines())
        body = loader.render_to_string(self.email_template, context)
        from_email = settings.DEFAULT_FROM_EMAIL
        to_email = user.email

        email_message = EmailMultiAlternatives(
            subject, body, from_email, [to_email])
        html_email = loader.render_to_string(self.email_template_html, context)
        email_message.attach_alternative(html_email, 'text/html')
        try:
            if settings.ENABLE_EMAIL:
                email_message.send()
                return

            logger.warning(to_email)
            logger.warning(body)

        except Exception as err:
            logger.error(err)
            return


class NotifyActivateUserByEmail(NotifyEmail):
    email_template_subject = 'registration/activate_user_subject.txt'
    email_template = 'registration/activate_user_email.txt'
    email_template_html = 'registration/activate_user_email.html'

    def get_email_context(self, user, token):
        context = super().get_email_context(user)
        if not token:
            token = default_token_generator.make_token(user)

        context['token'] = token

        return context


class SubscriptionEmail(NotifyEmail):

    def get_email_context(self, user, token):
        context = super().get_email_context(user)
        if not self.lot:
            self.get_lot()
        context['lot'] = self.lot

        return context

    def template_subscriptor(self, form):

        if form._type == "circuit_manager":
            base = "circuit_manager"
        if form._type == "shop":
            base = "shop"

        self.email_template_subject = f'{base}/subscription_subject.txt'
        self.email_template = f'{base}/subscription_email.txt'
        self.email_template_html = f'{base}/subscription_email.html'


class DonorEmail(NotifyEmail):
    email_template_subject = 'donor/subject.txt'
    email_template = 'donor/email.txt'
    email_template_html = 'donor/email.html'

    def get_email_context(self, user, token):
        context = super().get_email_context(user)
        if not token:
            token = default_token_generator.make_token(user)

        context['token'] = token

        return context
