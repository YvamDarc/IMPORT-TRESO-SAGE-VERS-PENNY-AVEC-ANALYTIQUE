import unittest,csv,io
from fusion import *

def pnmline(ac='606100',n='100',kind=' ',sub='',ref='42',dt='150326',sid='1'):
    s=list(' '*199)
    for start,size,val in [(0,3,'60'),(3,6,dt),(9,2,'FF'),(11,13,ac),(24,1,kind),(25,13,sub),(38,13,ref),(51,25,'FACTURE TEST'),(83,1,'D' if D(n)>0 else 'C'),(84,20,str(abs(D(n)))),(104,1,'N'),(105,7,sid),(138,3,'EUR'),(164,10,'1' if kind=='A' else '')]:s[start:start+size]=val.ljust(size)
    return ''.join(s)
def fixture(duplicate=False):
    fields=['JournalCode','EcritureNum','EcritureDate','CompteNum','CompAuxNum','PieceRef','PieceDate','EcritureLib','Debit','Credit']
    rows=[];lines=[]
    for i in range(2 if duplicate else 1):
        rows.extend([['60',f'E{i}','20260315','606100','',f'FACT-{i}','20260310','FACTURE TEST','100','0'],['60',f'E{i}','20260315','401000','401TEST',f'FACT-{i}','20260310','FACTURE TEST','0','100']])
        lines.extend([pnmline(ref=str(42+i)),pnmline(kind='A',sub=f'VEHICULE{i}',ref=str(42+i)),pnmline(ac='401000',n='-100',kind='X',sub='401TEST',ref=str(42+i),sid='2')])
    out=io.StringIO();w=csv.writer(out,delimiter='\t');w.writerow(fields);w.writerows(rows)
    return out.getvalue().encode(),('DEMO\n'+'\n'.join(lines)).encode('cp850')
class Tests(unittest.TestCase):
    def test_actual_date_and_two_references(self):
        r=reconcile(*fixture());rows,rep,_=make_export(r)
        self.assertEqual(rows[0]['Date'],'15/03/2026');self.assertEqual(rows[0]['Date pièce FEC'],'20260310')
        self.assertEqual(rows[0]['Numéro interne Sage'],'42');self.assertEqual(rows[0]['Référence facture FEC'],'FACT-0')
        self.assertEqual(rep['dates_modifiees'],0)
    def test_ambiguous_not_guessed(self):
        r=reconcile(*fixture(True));self.assertEqual(len(r[-1]),4)
        rows,_,_=make_export(r);self.assertTrue(all(not x['Numéro interne Sage'] for x in rows))
        self.assertIn('À RAPPROCHER — REPRISE',[x['Catégorie'] for x in rows])
    def test_manual_assignment(self):
        r=reconcile(*fixture(True),manual={'2':2});self.assertEqual(r[2][2],2)
        self.assertEqual(make_export(r)[0][0]['Catégorie'],'VEHICULE0')
    def test_incompatible_assignment(self):
        with self.assertRaises(ConversionError):reconcile(*fixture(),manual={'2':4})
    def test_different_file_blocked(self):
        f,p=fixture()
        with self.assertRaises(ConversionError):reconcile(f.replace(b'20260315',b'20260415'),p)
    def test_no_silent_skip(self):
        r=reconcile(*fixture(True))
        with self.assertRaises(ConversionError):make_export(r,pending=False)
    def test_totals(self):
        r=reconcile(*fixture());rows,rep,_=make_export(r)
        self.assertEqual(rep['debit'],'100,00');self.assertEqual(rep['credit'],'100,00')
    def test_utf8_and_tab(self):
        f,p=fixture();self.assertEqual(len(read_fec(f)),2)
if __name__=='__main__':unittest.main()
