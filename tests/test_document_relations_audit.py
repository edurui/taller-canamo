"""Concrete audit regressions; all records are synthetic in temporary SQLite."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from taller.app import App
from taller.errors import AppError


def save(app, customer, kind='invoice', **extra):
    return app.dispatch('documents.save', {'data':{
        'kind':kind,'customer_id':customer['id'],
        'lines':[{'description':'Trabajo sintético','quantity':'1','unit_price':'100','tax_rate':'21'}],
        **extra,
    }})


def issue(app, document):
    return app.dispatch('documents.publish', {'identifier':document['id'],'expected_version':document['version']})


@pytest.mark.parametrize('published', [False, True])
def test_void_is_blocked_by_draft_or_issued_rectification_without_side_effects(app, customer, published):
    original=issue(app,save(app,customer))
    correction=app.dispatch('documents.rectify', {'identifier':original['id'],'reason':'Devolución sintética'})
    if published:
        correction=issue(app,correction)
    before=(app.dashboard(),app.settings.list_series(),app.fiscal.records())
    with pytest.raises(AppError) as caught:
        app.dispatch('documents.void', {'identifier':original['id'],'reason':'Error material sintético','confirmation':'ANULAR'})
    assert caught.value.code=='rectifications_exist'
    assert caught.value.details==[{'id':correction['id'],'status':correction['status'],'full_number':correction['full_number']}]
    assert (app.dashboard(),app.settings.list_series(),app.fiscal.records())==before
    assert app.documents.get(original['id'])['status']=='issued'
    assert app.documents.get(correction['id'])['status']==correction['status']


@pytest.mark.parametrize('published', [False, True])
def test_original_can_be_voided_after_resolving_rectification(app, customer, published):
    original=issue(app,save(app,customer))
    correction=app.documents.rectify(original['id'],'Devolución sintética')
    if published:
        correction=issue(app,correction)
        app.documents.void(correction['id'],'Rectificativa creada por error','ANULAR')
    else:
        app.documents.delete_draft(correction['id'])
    assert not app.documents.get(original['id'])['active_rectifications']
    assert app.documents.void(original['id'],'Error material sintético','ANULAR')['status']=='void'
    assert app.fiscal.verify_chain()['ok']


def test_void_checks_descendants_and_concurrent_rectification(app, customer):
    original=issue(app,save(app,customer))
    first=issue(app,app.documents.rectify(original['id'],'Corrección sintética'))
    second=app.documents.rectify(first['id'],'Corrección de la anterior')
    assert {item['id'] for item in app.documents.get(original['id'])['active_rectifications']}=={first['id'],second['id']}
    with pytest.raises(AppError) as caught:
        app.documents.void(first['id'],'Error material sintético','ANULAR')
    assert caught.value.code=='rectifications_exist'

    other=issue(app,save(app,customer))
    barrier=Barrier(2)
    clients=[App(app.db.root),App(app.db.root)]
    def operation(rectify):
        client=clients[int(rectify)]
        barrier.wait(timeout=5)
        try:
            return client.documents.rectify(other['id'],'Corrección concurrente') if rectify else client.documents.void(other['id'],'Error concurrente','ANULAR')
        except AppError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(operation,[True,False]))
    assert sum(isinstance(item,AppError) for item in results)==1
    current=app.documents.get(other['id'])
    assert (current['status']=='void' and not current['active_rectifications']) or (
        current['status']=='issued' and len(current['active_rectifications'])==1)


@pytest.mark.parametrize('mismatch', ['customer','vehicle','draft_origin','invoice_origin'])
def test_rpc_cannot_invent_inconsistent_conversion_origin(app, customer, mismatch):
    vehicle=app.contacts.save_vehicle({'customer_id':customer['id'],'plate':'1234 BBB'})
    source=save(app,customer,'invoice' if mismatch=='invoice_origin' else 'quote',vehicle_id=vehicle['id'])
    if mismatch!='draft_origin':
        source=issue(app,source)
    extra={'origin_id':source['id'],'vehicle_id':vehicle['id']}
    target_customer=customer
    if mismatch=='customer':
        target_customer=app.contacts.save_customer({'name':'Cliente sintético distinto'})
        extra['vehicle_id']=None
    elif mismatch=='vehicle':
        extra['vehicle_id']=None
    with pytest.raises(AppError) as caught:
        save(app,target_customer,**extra)
    assert caught.value.code in ('conversion_origin','conversion_identity')
    with app.db.read() as conn:
        assert conn.execute('SELECT count(*) FROM documents').fetchone()[0]==1


def test_converted_draft_keeps_origin_and_customer_vehicle_identity(app, customer):
    vehicle=app.contacts.save_vehicle({'customer_id':customer['id'],'plate':'1234 BBB'})
    quote=issue(app,save(app,customer,'quote',vehicle_id=vehicle['id']))
    invoice=app.documents.convert(quote['id'])
    assert invoice['conversion_identity_locked']
    other=app.contacts.save_customer({'name':'Cliente sintético distinto'})
    for changes in ({'origin_id':None},{'customer_id':other['id'],'vehicle_id':None},{'vehicle_id':None}):
        with pytest.raises(AppError) as caught:
            app.dispatch('documents.save', {'data':{**invoice,**invoice['payload'],**changes}})
        assert caught.value.code in ('conversion_origin','conversion_identity')
    assert app.documents.convert(quote['id'])['customer_id']==customer['id']
    assert app.documents.get(invoice['id'])['version']==invoice['version']
    # Omitting an internal relationship on an otherwise valid edit preserves it.
    data={**invoice,**invoice['payload'],'notes':'Texto editable'}
    del data['origin_id']
    assert app.documents.save(data)['origin_id']==quote['id']


def test_published_order_cannot_change_identity_after_conversion(app, customer):
    order=issue(app,save(app,customer,'order'))
    invoice=app.documents.convert(order['id'])
    assert app.documents.get(order['id'])['conversion_identity_locked']
    other=app.contacts.save_customer({'name':'Otro cliente sintético'})
    with pytest.raises(AppError) as caught:
        app.documents.save({**order,**order['payload'],'customer_id':other['id']})
    assert caught.value.code=='conversion_identity'
    assert app.documents.convert(order['id'])['id']==invoice['id']
    # Unrelated orders remain editable, including their selected customer.
    unlinked=issue(app,save(app,customer,'order'))
    assert not unlinked['conversion_identity_locked']
    assert app.documents.save({**unlinked,**unlinked['payload'],'customer_id':other['id']})['customer_id']==other['id']


def test_conversion_rejects_legacy_inconsistent_family_and_second_invoice(app, customer):
    quote=issue(app,save(app,customer,'quote'))
    order=issue(app,app.documents.convert(quote['id'],'order'))
    invoice=app.documents.convert(order['id'])
    with pytest.raises(AppError) as caught:
        save(app,customer,origin_id=quote['id'])
    assert caught.value.code=='conversion_conflict'
    other=app.contacts.save_customer({'name':'Cliente legado sintético'})
    # Reproduce a draft written by the version that allowed a cross-customer link.
    with app.db.transaction() as conn:
        conn.execute('UPDATE documents SET customer_id=? WHERE id=?',(other['id'],invoice['id']))
    for action,params in [('documents.convert',{'identifier':quote['id']}),('documents.publish',{'identifier':invoice['id']})]:
        with pytest.raises(AppError) as caught:
            app.dispatch(action,params)
        assert caught.value.code=='conversion_identity'
    assert app.documents.get(invoice['id'])['full_number'] is None
    assert not app.fiscal.records()
