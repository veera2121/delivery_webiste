"""Financial adjustments; no commits here. Caller owns transaction.

Settlement deltas use the ORIGINAL snapshot commission rate. New items use
current restaurant terms. Existing snapshots never change.
"""
from decimal import Decimal
from uuid import uuid4
from settlement_service import money, calculate_line, get_restaurant_commission_percent
from models import (SettlementLine, SettlementAdjustment, CustomerPaymentAdjustment,
                    RestaurantSettlementTerms)

ZERO = Decimal('0.00')


def _values(restaurant_price, customer_price, qty, rate):
    if qty == 0:
        return dict(restaurant_gross=ZERO, customer_item_value=ZERO,
                    markup_amount=ZERO, commission_amount=ZERO, restaurant_payable=ZERO)
    return calculate_line(restaurant_price, customer_price, qty, rate)


def record_item_changes(db, order, before, after, reason, actor, edit_key):
    """before/after: dict[item_id] = (quantity, price, is_removed).

    All edits are priced at the saved order-item unit price. No price-edit support.
    For original items, the snapshot's rate is used; for newly added items,
    the restaurant's current commission rate is used.
    """
    all_ids = set(before) | set(after)
    for item_id in sorted(all_ids):
        old_qty, old_price, old_removed = before.get(item_id, (0, ZERO, True))
        new_qty, new_price, new_removed = after.get(item_id, (0, old_price, True))
        old_qty = 0 if old_removed else int(old_qty)
        new_qty = 0 if new_removed else int(new_qty)
        if old_qty == new_qty and money(old_price) == money(new_price):
            continue
        if old_qty and new_qty and money(old_price) != money(new_price):
            raise ValueError('Changing existing item prices is not supported by this adjustment service.')
        line = SettlementLine.query.filter_by(order_item_id=item_id).first()
        if line:
            rate = line.commission_percent
            unit_price = money(line.customer_unit_price)
            restaurant_price = money(line.restaurant_unit_price)
            # Reject mismatches rather than applying a different pricing policy.
            if (old_qty and money(old_price) != unit_price) or (new_qty and money(new_price) != unit_price):
                raise ValueError('Order item price differs from settlement snapshot; manual financial review required.')
        else:
            previous = SettlementAdjustment.query.filter_by(
                order_item_id=item_id
            ).order_by(SettlementAdjustment.id.asc()).first()
            rate = (previous.commission_percent if previous else
                    get_restaurant_commission_percent(RestaurantSettlementTerms, order.restaurant_id))
            unit_price = money(new_price if new_qty else old_price)
            restaurant_price = unit_price
        old_values = _values(restaurant_price, unit_price, old_qty, rate)
        new_values = _values(restaurant_price, unit_price, new_qty, rate)
        fields = {
            'gross_delta': money(new_values['restaurant_gross'] - old_values['restaurant_gross']),
            'customer_item_delta': money(new_values['customer_item_value'] - old_values['customer_item_value']),
            'markup_delta': money(new_values['markup_amount'] - old_values['markup_amount']),
            'commission_delta': money(new_values['commission_amount'] - old_values['commission_amount']),
            'payable_delta': money(new_values['restaurant_payable'] - old_values['restaurant_payable']),
        }
        if all(v == ZERO for v in fields.values()):
            continue
        db.session.add(SettlementAdjustment(
            order_id=order.id, order_item_id=item_id, restaurant_id=order.restaurant_id,
            source_settlement_line_id=line.id if line else None,
            operation_key=f'{edit_key}:item:{item_id}', reason=reason,
            created_by=actor, commission_percent=rate, **fields,
        ))


def record_customer_balance(db, order, old_total, new_total, reason, actor, edit_key, payment_finalized):
    """Create a pending cash movement ONLY if money has already been finalized.
    This does not process refunds or collections. Never fake payment status.
    """
    difference = money(new_total) - money(old_total)
    if not payment_finalized or difference == ZERO:
        return None
    movement = CustomerPaymentAdjustment(
        order_id=order.id, operation_key=f'{edit_key}:payment',
        kind='collection_due' if difference > 0 else 'refund_due',
        amount=abs(difference), status='pending', reason=reason, created_by=actor,
    )
    db.session.add(movement)
    return movement


def new_edit_key():
    return str(uuid4())
