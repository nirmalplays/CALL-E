from ocr.draft import medication_drafts
from tests.test_local_api import client
from tests.test_ocr_upload import document


def test_drafts_follow_input_without_default_medicines():
    def draft(text):
        return medication_drafts([{'page':1,'lines':[{'text':text,'confidence':0.9}]}])
    a=draft('Tab Zeta 12.5 mg; quantity: 2 tablets; schedule: after lunch; duration: 3 days')
    b=draft('Capsule Omega 250 mcg')
    assert a[0]['name']=='Zeta' and a[0]['dosage']=='12.5 mg'
    assert a[0]['quantity']=='2 tablets' and a[0]['schedule']==['after lunch']
    assert b[0]['name']=='Omega' and b[0]['dosage']=='250 mcg'
    assert b[0]['quantity']=='' and b[0]['duration']=='' and b[0]['schedule']==[]
    assert draft('Unreadable prescription')==[]


def test_actual_upload_retains_source_and_reopens(client):
    data=document()
    r=client.post('/local/ocr/extract',content=data)
    assert r.status_code==200,r.text
    scan=r.json()
    assert scan['draft_medications'][0]['name']=='Medicine Alpha'
    assert scan['draft_medications'][0]['dosage']=='500 mg'
    key=scan['scan_id']
    assert client.get('/local/ocr').json()[0]['scan_id']==key
    assert client.get('/local/ocr/'+key).json()['draft_medications']==scan['draft_medications']
    assert client.get('/local/ocr/'+key+'/source').content==data
    assert client.get('/local/ocr/'+key+'/source',headers={'Authorization':''}).status_code==401
