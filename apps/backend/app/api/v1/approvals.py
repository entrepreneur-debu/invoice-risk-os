"""Approval queue: invoices awaiting a decision the current user may take."""

from fastapi import APIRouter, Depends

from app.api.deps import DbDep, TenantDep
from app.api.v1.common import Page, Pagination
from app.modules.invoices import service
from app.modules.invoices.schemas import InvoiceSummary
from app.modules.review import service as review

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=Page[InvoiceSummary])
def approval_queue(ctx: TenantDep, db: DbDep, page: Pagination = Depends()) -> Page[InvoiceSummary]:
    invoices, total = review.approval_queue(db, ctx, page.limit, page.offset)
    ids = [i.id for i in invoices]
    summaries, _ = service.list_invoices(
        db,
        ctx,
        status=None,
        risk_level=None,
        vendor_id=None,
        query=None,
        limit=len(ids) or 1,
        offset=0,
        ids=ids,
    )
    by_id = {s.id: s for s in summaries}
    return Page(
        items=[by_id[i.id] for i in invoices if i.id in by_id],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
