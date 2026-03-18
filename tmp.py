import pandas as pd
import warnings
warnings.filterwarnings('ignore')
from connections.connect import make_engine
from connections.config import MYSQL_DATABASE
engine = make_engine(MYSQL_DATABASE)
df = pd.read_sql("SELECT * FROM vw_commission_gadd WHERE DATE(created_at) = '2026-03-15' AND group_name='BA Classiques & BA AGENCE'", engine)
print(df[['user_name', 'created_at', 'periode_nom', 'taux_gadd', 'nb_total', 'amt_total']].head())
