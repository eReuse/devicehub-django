import logging

from django.conf import settings
from django.template import loader
from django.urls import reverse_lazy
from django.core.mail import EmailMultiAlternatives
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site


logger = logging.getLogger(__name__)


class NotifyEmail:
    email_template_subject = ''
    email_template = ''
    email_template_html = ''
    lot = None

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
            'lot': self.lot,
        }
        return context

    def send_email(self, user, msg=''):
        """
        Send a email when a user is activated.
        """
        body = msg
        html_email = msg.replace("\n", "<br />")
        context = self.get_email_context(user)
        subject = loader.render_to_string(self.email_template_subject, context)
        # Email subject *must not* contain newlines
        subject = ''.join(subject.splitlines())
        if not msg:
            body = loader.render_to_string(self.email_template, context)
            html_email = loader.render_to_string(self.email_template_html, context)
        from_email = settings.DEFAULT_FROM_EMAIL
        to_email = user.email

        email_message = EmailMultiAlternatives(
            subject, body, from_email, [to_email])
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

    def get_email_context(self, user):
        context = super().get_email_context(user)
        # if not token:
        #     token = default_token_generator.make_token(user)

        # context['token'] = token

        return context


class SubscriptionEmail(NotifyEmail):

    def get_email_context(self, user):
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

    def get_email_context(self, user):
        context = super().get_email_context(user)
        if not self.lot:
            self.get_lot()

        protocol = context.get("protocol", "")
        domain = context.get("domain", "")
        path = reverse_lazy("lot:web_donor", args=[self.lot.id, user.id])
        web_donor = f"{protocol}://{domain}{path}"
        context['web_donor'] = web_donor

        return context


class BeneficiaryEmail(NotifyEmail):

    def get_email_context(self, user):
        context = super().get_email_context(user)
        if not self.lot:
            self.get_lot()

        protocol = context.get("protocol", "")
        domain = context.get("domain", "")
        path = reverse_lazy(
            "lot:web_beneficiary",
            args=[self.lot.id, self.beneficiary.id]
        )

        web_beneficiary = f"{protocol}://{domain}{path}"
        context['web_beneficiary'] = web_beneficiary
        context["beneficiary"] = self.beneficiary
        context["lot"] = self.lot

        return context


class BeneficiaryAgreementEmail(BeneficiaryEmail):
    email_template_subject = 'beneficiary/agreement/subject.txt'
    email_template = 'beneficiary/agreement/email.txt'
    email_template_html = 'beneficiary/agreement/email.html'


class BeneficiaryConfirmEmail(BeneficiaryEmail):
    email_template_subject = 'beneficiary/confirm/subject.txt'
    email_template = 'beneficiary/confirm/email.txt'
    email_template_html = 'beneficiary/confirm/email.html'


class BeneficiaryDeliveryEmail(BeneficiaryEmail):
    email_template_subject = 'beneficiary/delivery/subject.txt'
    email_template = 'beneficiary/delivery/email.txt'
    email_template_html = 'beneficiary/delivery/email.html'


class BeneficiaryReturnEmail(BeneficiaryEmail):
    email_template_subject = 'beneficiary/return/subject.txt'
    email_template = 'beneficiary/return/email.txt'
    email_template_html = 'beneficiary/return/email.html'
