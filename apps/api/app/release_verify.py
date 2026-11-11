"""Local operator entry point for recording inspection of an exact release file."""
import argparse
import json

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .db import Record, Session
from .reconcile import local_database_only
from .release import rules_fingerprint, ruleset, verify_label


def main(argv=None):
    parser=argparse.ArgumentParser(description='登记人工检查过的发布标识，默认只预检。')
    for name in ('workspace','asset-id','release-sha256','rule-sha256','reviewer','evidence'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--asset-revision',type=int,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args(argv)
    try:
        local_database_only()
        rules=ruleset()
        if rules_fingerprint(rules)!=args.rule_sha256:raise ValueError('RULESET_CHANGED')
        with Session.begin() as session:
            asset=session.scalar(select(Record).where(
                Record.id==args.asset_id,Record.workspace==args.workspace,Record.kind=='asset',
            ).with_for_update())
            if not asset or asset.data.get('deleting'):raise ValueError('ASSET_NOT_AVAILABLE')
            verification=verify_label(asset,rules,args.asset_revision,args.release_sha256,args.reviewer,args.evidence)
            if args.apply:
                asset.data={**asset.data,'label_verification':verification}
        print(json.dumps({'asset_id':args.asset_id,'mode':'applied' if args.apply else 'dry_run'}))
        return 0
    except ValueError as error:
        print(json.dumps({'error':str(error)}))
        return 1
    except SQLAlchemyError:
        print(json.dumps({'error':'DATABASE_ERROR'}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
