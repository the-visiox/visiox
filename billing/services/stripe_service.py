"""
Stripe integration service.
Requires STRIPE_SECRET_KEY in environment.
"""
import stripe
from django.conf import settings
from django.utils import timezone

stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeService:
    @staticmethod
    def get_or_create_customer(team, email: str) -> str:
        from billing.models import Subscription

        subscription = Subscription.objects.filter(team=team).first()
        if subscription and subscription.stripe_customer_id:
            return subscription.stripe_customer_id

        customer = stripe.Customer.create(
            email=email,
            name=team.name,
            metadata={'team_id': team.id},
        )
        return customer['id']

    @staticmethod
    def create_subscription(team, plan, user_email: str) -> dict:
        from billing.models import Subscription

        if not plan.stripe_price_id:
            raise ValueError(f"Plan '{plan.name}' has no Stripe price ID configured.")

        customer_id = StripeService.get_or_create_customer(team, user_email)
        stripe_sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{'price': plan.stripe_price_id}],
            metadata={'team_id': team.id, 'plan_id': plan.id},
        )

        sub, _ = Subscription.objects.update_or_create(
            team=team,
            defaults={
                'plan': plan,
                'stripe_customer_id': customer_id,
                'stripe_subscription_id': stripe_sub['id'],
                'status': stripe_sub['status'],
                'current_period_start': timezone.datetime.fromtimestamp(
                    stripe_sub['current_period_start'], tz=timezone.utc
                ),
                'current_period_end': timezone.datetime.fromtimestamp(
                    stripe_sub['current_period_end'], tz=timezone.utc
                ),
            },
        )
        return sub

    @staticmethod
    def cancel_subscription(subscription) -> None:
        if subscription.stripe_subscription_id:
            stripe.Subscription.cancel(subscription.stripe_subscription_id)
        subscription.status = 'cancelled'
        subscription.cancelled_at = timezone.now()
        subscription.save(update_fields=['status', 'cancelled_at'])

    @staticmethod
    def record_usage(subscription, usage_type: str, quantity: float) -> None:
        from billing.models import UsageRecord
        UsageRecord.objects.create(
            team=subscription.team,
            type=usage_type,
            quantity=quantity,
        )

    @staticmethod
    def handle_webhook_event(payload: bytes, sig_header: str) -> dict:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
        from billing.models import Subscription

        if event['type'] == 'customer.subscription.updated':
            stripe_sub = event['data']['object']
            Subscription.objects.filter(
                stripe_subscription_id=stripe_sub['id']
            ).update(
                status=stripe_sub['status'],
                current_period_end=timezone.datetime.fromtimestamp(
                    stripe_sub['current_period_end'], tz=timezone.utc
                ),
            )
        elif event['type'] == 'customer.subscription.deleted':
            stripe_sub = event['data']['object']
            Subscription.objects.filter(
                stripe_subscription_id=stripe_sub['id']
            ).update(status='cancelled', cancelled_at=timezone.now())

        return {'type': event['type'], 'handled': True}
