from django.db.models import Q


def project_access_q(user, prefix: str = '') -> Q:
    """Q filter for objects a user can reach through their Project.

    Access = the project owner, the project's team owner, or a member of that
    team. ``prefix`` is the ORM relation path from the queried model to Project,
    e.g. 'media__dataset__project__' (must end with '__', or be empty when the
    model *is* the Project).
    """
    return (
        Q(**{f'{prefix}owner': user})
        | Q(**{f'{prefix}team__owner': user})
        | Q(**{f'{prefix}team__members__user': user})
    )
