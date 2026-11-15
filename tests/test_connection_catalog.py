import copy,threading
from novoacesso.identity import IdentityStore
from novoacesso.relay import token_encode
from novoacesso.connection_catalog import consolidate_connections,remember_recent
from novoacesso.saved_connections import save_address,save_connection,remember_authorized,list_connections,open_connection

def profile(fp='ab'*32,port=4433):return token_encode('NAU1-',dict(v=1,host='127.0.0.1',port=port,fp=fp))

def test_address_and_authorized_notebook_merge_and_recent_reconnects_stay_single(tmp_path):
    store=IdentityStore(tmp_path);id=save_connection(store,'NOTEBOOK',profile())
    store.data['connections'][id]['address']='736908531099'
    store.data['connections']['duplicate']=dict(kind='address',address='736908531099',name='PC 736908531099',locked=False)
    store.configure(desk_recents=[dict(label='7369 0853 1099',fixed=True,saved_id='duplicate',when='15/11 12:01'),dict(label='Computador autorizado',saved_id=id,when='15/11 11:01')])
    aliases=consolidate_connections(store)
    assert aliases=={'duplicate':id}
    assert len(list_connections(store))==1 and list_connections(store)[0]['name']=='NOTEBOOK'
    assert open_connection(store,id)==profile()
    assert len(store.settings()['desk_recents'])==1 and store.settings()['desk_recents'][0]['saved_id']==id
    assert list((tmp_path/'backups').glob('*.dat'))
    remember_recent(store,dict(label='Computador autorizado',saved_id=id,when='15/11 13:01'))
    assert len(store.settings()['desk_recents'])==1 and store.settings()['desk_recents'][0]['when']=='15/11 13:01'
    assert save_address(store,'PC 736908531099','7369 0853 1099')==id
    assert list_connections(store)[0]['name']=='NOTEBOOK'

def test_merge_retains_locked_entry_id_ciphertext_password_and_permissions(tmp_path):
    store=IdentityStore(tmp_path);id=save_connection(store,'NOTEBOOK',profile(),'senha-local-123')
    sealed=store.data['connections'][id]['sealed'];before=copy.deepcopy(store.data['trusted'])
    store.data['connections']['plain']=dict(kind='authorized',locked=False,name='PC',peer_fp='ab'*32,profile=profile(port=4444),address='736908531099')
    consolidate_connections(store)
    assert list(store.data['connections'])==[id] and store.data['connections'][id]['sealed']==sealed
    assert open_connection(store,id,'senha-local-123')==profile()
    save_connection(store,'NOTEBOOK',profile(port=5555))
    assert store.data['connections'][id]['locked'] and store.data['connections'][id]['sealed']==sealed
    assert store.data['trusted']==before and not store.settings().get('unattended')

def test_different_fingerprints_never_merge_by_name_or_address(tmp_path):
    store=IdentityStore(tmp_path)
    one=save_connection(store,'Mesmo nome',profile('ab'*32));two=save_connection(store,'Mesmo nome',profile('cd'*32))
    for id in (one,two):store.data['connections'][id]['address']='736908531099'
    store.data['connections']['plain']=dict(kind='address',locked=False,name='Número',address='736908531099')
    consolidate_connections(store)
    assert len(store.data['connections'])==3
    assert open_connection(store,one)!=open_connection(store,two)

def test_unknown_legacy_locked_entry_does_not_block_saving_other_computer(tmp_path):
    store=IdentityStore(tmp_path)
    store.data.setdefault('connections',{})['legacy']=dict(name='Antigo',locked=True,sealed='not-decrypted',kind='authorized')
    id=remember_authorized(store,'Novo PC',profile(),'228784030709')
    assert id and id!='legacy' and open_connection(store,id)==profile()
    assert store.data['connections']['legacy']['sealed']=='not-decrypted'

def test_multiple_computers_keep_separate_favorites_and_recents(tmp_path):
    store=IdentityStore(tmp_path)
    one=save_address(store,'Notebook','736908531099');two=save_address(store,'Outro PC','228784030709')
    for id,number in [(one,'736908531099'),(two,'228784030709'),(one,'736908531099')]:
        remember_recent(store,dict(label=number,fixed=True,saved_id=id))
    assert len(list_connections(store))==2 and len(store.settings()['desk_recents'])==2
