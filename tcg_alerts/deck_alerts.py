"""Budget transitions require fresh, confirmed prices for every missing copy."""
from .core import now,money
from .decks import DeckStore


def evaluate(db):
    store=DeckStore(db);history=db.setting('deck_budget_alerts',[]);added=[]
    for deck in store.decks():
        key='deck_budget_'+str(deck['id']);rule=db.setting(key,{})
        if not rule.get('enabled') or rule.get('currency')!=deck['currency']:continue
        report=store.report(deck['id']);s=report['summary']
        active=bool(s['missing'] and s['missing_ask_copies']==s['missing'] and s['missing_ask_subtotal']<=rule['amount'])
        if active and not rule.get('active'):
            event=dict(at=now(),game=deck['game'],deck_id=deck['id'],kind='Deck budget',message=f"{deck['name']}: all {s['missing']} missing copies have fresh linked asking prices; subtotal {deck['currency']} {s['missing_ask_subtotal']/100:.2f} meets {rule['amount']/100:.2f} budget. Shipping excluded; seller quantities unverified.")
            added.append(event)
        if bool(rule.get('active'))!=active:db.set_setting(key,dict(rule,active=active))
    if added:db.set_setting('deck_budget_alerts',(added+history)[:100])
    return added


def configure(page):
    if not page.current:return
    from .additions import Form
    deck=page.current;key='deck_budget_'+str(deck['id']);old=page.app.db.setting(key,{})
    fields=[('enabled','Budget notifications','On' if old.get('enabled') else 'Off',('On','Off')),('amount','Missing-card item budget ('+deck['currency']+', excludes shipping)',f"{old.get('amount',0)/100:.2f}",None)]
    def save(value):
        amount=money(value['amount'])
        page.app.db.set_setting(key,dict(enabled=value['enabled']=='On',amount=amount,currency=deck['currency'],active=False))
        page.app.status.set('Deck budget saved. Alerts require fresh linked asks for every missing copy; shipping and seller quantities remain unverified.')
        page.app.refresh()
    return Form(page.app,'Missing-card budget alert',fields,save)
