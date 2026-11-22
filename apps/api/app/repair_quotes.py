"""Bind a paid repair to the current model configuration and reservation."""
import hashlib
import json

from .execution import Budget
from .db import Record
from .ledger import money


def quote_repair(session, workspace, work):
    from marketing_worker.business import authorization_snapshot

    try:
        config = authorization_snapshot(workspace, work.data['creation_request_id'])
        if config['providers']['image'] != 'MiniMax-H3-Image':
            return {'executable': False, 'blocker': 'REPAIR_MODEL_NOT_CONFIGURED'}, None
        bound = money(config['bounds']['product_image'])
        budget = session.get(Budget, config['budget_id'])
        if not budget or budget.workspace != workspace or budget.cap - budget.reserved - budget.settled < bound:
            return {'executable': False, 'blocker': 'BUDGET_INSUFFICIENT'}, None
        hold = session.get(Record, 'budget-hold:' + budget.id)
        if hold and hold.workspace == workspace and hold.kind == 'budget_hold' and hold.data.get('active'):
            return {'executable': False, 'blocker': 'BUDGET_HELD_FOR_REVIEW'}, None
    except (KeyError, ValueError):
        return {'executable': False, 'blocker': 'REPAIR_MODEL_NOT_CONFIGURED'}, None
    reference = hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()
    return {'executable': True, 'quote_id': reference, 'cost_upper_bound': str(bound)}, config
