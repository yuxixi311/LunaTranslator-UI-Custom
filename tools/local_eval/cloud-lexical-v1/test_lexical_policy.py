import unittest
from lexical_policy import admitted_entries
PERSON=['名詞','固有名詞','人名','名','*','*']
NOUN=['名詞','普通名詞','一般','*','*','*']
def token(text,a,b,pos=PERSON,oov=False):
 return dict(start=a,end=b,raw_surface=text[a:b],pos=list(pos),is_oov=oov,dictionary_id=-1 if oov else 0)
class Contract(unittest.TestCase):
 def test_person(self):
  self.assertEqual(admitted_entries('光',[token('光',0,1)],['光']),['光'])
 def test_mixed_entry_all_occurrences(self):
  self.assertEqual(admitted_entries('光 光',[token('光 光',0,1),token('光 光',2,3,NOUN)],['光']),[])
 def test_repeat_person(self):
  self.assertEqual(admitted_entries('光 光',[token('光 光',0,1),token('光 光',2,3)],['光']),['光'])
 def test_oov(self):
  self.assertEqual(admitted_entries('光',[token('光',0,1,oov=True)],['光']),[])
 def test_partial(self):
  self.assertEqual(admitted_entries('光線',[token('光線',0,2)],['光']),[])
 def test_no_match(self):
  self.assertEqual(admitted_entries('空',[token('空',0,1,NOUN)],['光']),[])
 def test_unicode_offsets(self):
  self.assertEqual(admitted_entries('😀 光',[token('😀 光',0,1,NOUN),token('😀 光',2,3)],['光']),['光'])
 def test_malformed(self):
  for tokens in ([],[token('光',0,1),token('光',0,1)],[dict(token('光',0,1),raw_surface='他')],[dict(token('光',0,1),dictionary_id=1)],[dict(token('光',0,1),pos=['名詞'])]):
   with self.subTest(tokens=tokens),self.assertRaises(ValueError):admitted_entries('光',tokens,['光'])
if __name__=='__main__':unittest.main()
