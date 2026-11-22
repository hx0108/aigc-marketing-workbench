"""Allocate a fixed merchant allowance from a separately funded platform pool."""
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from .execution import Budget

POOL_ID = 'merchant-sponsorship-pool'
POOL_OWNER = 'platform-sponsorship'


def allocate(sessions, workspace, allowance):
    cap = Decimal(str(allowance))
    if not cap.is_finite() or cap <= 0 or cap != cap.quantize(Decimal('.01')):
        raise ValueError('invalid_sponsored_allowance')
    identifier = 'sponsored:' + workspace
    try:
        with sessions.begin() as session:
            if session.get(Budget, identifier):
                return identifier
            transfer = session.execute(update(Budget).where(
                Budget.id == POOL_ID, Budget.workspace == POOL_OWNER,
                Budget.cap - Budget.reserved - Budget.settled >= cap
            ).values(cap=Budget.cap-cap))
            if transfer.rowcount != 1:
                if session.get(Budget, identifier):
                    return identifier
                raise ValueError('sponsorship_exhausted')
            session.add(Budget(id=identifier, workspace=workspace, cap=cap))
    except IntegrityError:
        # A concurrent first request won. The duplicate transfer rolled back.
        with sessions() as session:
            if not session.get(Budget, identifier):
                raise
    return identifier


def sponsored_configuration(workspace, base):
    from marketing_worker.configuration import compose_configuration, read_credentials
    template = base['template']
    budget = allocate(base['sessions'], workspace, template['merchant_allowance_cny'])
    settings = dict(template, workspace=workspace, sources={}, budget_id=budget,
                    consent_version=template['consent_version']+'-sponsored')
    return compose_configuration(settings, read_credentials(template['credentials_file']), base['sessions'])
