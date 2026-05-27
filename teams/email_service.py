from django.conf import settings
from django.core.mail import send_mail


def send_invitation_email(invitation):
    accept_url = f"{settings.FRONTEND_URL}/invite/{invitation.token}"
    team_name = invitation.team.name
    inviter = invitation.invited_by.username if invitation.invited_by else "Someone"
    role = invitation.role.capitalize()

    subject = f"You're invited to join {team_name} on VisioX"
    text_body = (
        f"Hi,\n\n"
        f"{inviter} has invited you to join the team \"{team_name}\" as a {role}.\n\n"
        f"Accept your invitation here:\n{accept_url}\n\n"
        f"This link expires in 7 days.\n\n"
        f"— The VisioX Team"
    )
    html_body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;background:#fff;border-radius:16px;border:1px solid #e7e5e4">
      <div style="margin-bottom:24px">
        <span style="display:inline-block;background:linear-gradient(135deg,#f97316,#fb923c);color:#fff;font-weight:800;font-size:18px;padding:6px 14px;border-radius:8px;letter-spacing:-0.5px">VisioX</span>
      </div>
      <h2 style="margin:0 0 8px;font-size:20px;font-weight:800;color:#1c1917">You're invited to join <span style="color:#f97316">{team_name}</span></h2>
      <p style="margin:0 0 24px;color:#78716c;font-size:14px">
        <strong style="color:#1c1917">{inviter}</strong> has invited you to join the team as a <strong style="color:#1c1917">{role}</strong>.
      </p>
      <a href="{accept_url}"
         style="display:inline-block;background:#f97316;color:#fff;font-weight:700;font-size:14px;padding:12px 28px;border-radius:10px;text-decoration:none;letter-spacing:-0.2px">
        Accept Invitation
      </a>
      <p style="margin:24px 0 0;color:#a8a29e;font-size:12px">This link expires in 7 days. If you did not expect this email, you can ignore it.</p>
    </div>
    """

    send_mail(
        subject=subject,
        message=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
        html_message=html_body,
        fail_silently=False,
    )
