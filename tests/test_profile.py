"""Identity edits and avatar ownership with disposable accounts; no provider IO."""
import io, os, sys, unittest
from pathlib import Path
from unittest.mock import patch
assert os.environ.get('RALLY_TESTING')=='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import service as s
from PIL import Image

class ProfileEdits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):s.initialize()
    def setUp(self):
        self.id=s.uid();self.handle='qa_'+self.id[:16]
        s.write('INSERT INTO accounts(id,handle,name,kind,bio,created) VALUES(?,?,?,?,?,?)',(self.id,self.handle,'Before','person','Original bio',s.now()))
        self.who={'user':self.id,'actor':self.id,'grant':None,'scopes':s.SCOPES}
    def save(self,**fields):return s.action('profile',self.who,fields)
    def photo(self):
        data=io.BytesIO();Image.new('RGB',(900,600),'blue').save(data,'PNG')
        return s.upload_file(self.who,data.getvalue(),'image/png',avatar=True)
    def test_canonical_identity_persists_and_omitted_fields_survive(self):
        p=self.save(handle=' @NEW_'+self.id[:10].upper()+' ',name=' New Name ')
        self.assertEqual(p['handle'],'new_'+self.id[:10]);self.assertEqual(p['name'],'New Name');self.assertEqual(p['bio'],'Original bio')
        self.assertEqual(s.profile(self.id)['handle'],p['handle'])
    def test_duplicate_handle_is_atomic(self):
        with self.assertRaises(s.Problem) as err:self.save(handle='rally',name='Must not persist',bio='Lost')
        self.assertEqual(err.exception.status,409);p=s.profile(self.id);self.assertEqual(p['name'],'Before');self.assertEqual(p['bio'],'Original bio')
    def test_invalid_name_does_not_partially_change_handle(self):
        for name in ['', ' '*4,'x'*49,None]:
            with self.assertRaises(s.Problem):self.save(handle='new_'+self.id[:10],name=name)
            self.assertEqual(s.profile(self.id)['handle'],self.handle)
    def test_avatar_is_normalized_owned_and_persisted(self):
        photo=self.photo();self.assertEqual(photo['mime'],'image/webp')
        file=s.one('SELECT path FROM media WHERE id=?',(photo['id'],))['path']
        with Image.open(s.STATE/'media'/file) as im:self.assertEqual(im.size,(512,512))
        self.assertEqual(self.save(avatarMedia=photo['id'])['avatar'],photo['url'])
        self.assertEqual(self.save(name='Next')['avatar'],photo['url'])
        self.assertEqual(self.save(avatarMedia='')['avatar'],'')
    def test_foreign_or_video_or_remote_avatar_rejected(self):
        photo=self.photo();s.write('UPDATE media SET actor=? WHERE id=?',('another',photo['id']))
        with self.assertRaises(s.Problem):self.save(avatarMedia=photo['id'],name='Not saved')
        self.assertEqual(s.profile(self.id)['name'],'Before')
        for bad in ['https://example.com/photo.jpg','../secret',{},'f'*32]:
            with self.assertRaises(s.Problem):self.save(avatarMedia=bad)
        with self.assertRaises(s.Problem):s.upload_file(self.who,b'video','video/mp4',avatar=True)
    def test_agent_cannot_edit_owner_profile_or_upload_avatar(self):
        self.who['grant']='qa-grant'
        with self.assertRaises(s.Problem):self.save(name='Agent')
        with self.assertRaises(s.Problem):self.photo()
    def test_invalid_image_and_oversize_rejected(self):
        for data in [b'invalid',b'0'*(5*1024*1024+1)]:
            with self.assertRaises(s.Problem):s.upload_file(self.who,data,'image/png',avatar=True)
    def test_avatar_error_does_not_commit_new_username(self):
        with self.assertRaises(s.Problem):self.save(handle='new_'+self.id[:10],avatarMedia='missing')
        self.assertEqual(s.profile(self.id)['handle'],self.handle)

if __name__=='__main__':unittest.main()
