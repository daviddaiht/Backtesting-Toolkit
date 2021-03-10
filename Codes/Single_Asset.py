import pandas as pd
import numpy as np
from datetime import date


class Single_Asset:
    def __init__(self, ann: int, rf: float, data=None):
        """
        Initialize a backtester for one single asset
        Think of it as sth that takes in a NAV series and spits out several stats
        Can't further impose positions on the NAV series
        :param int ann: number of days used to annualize statistics, e.g. 250 or 252
        :param float rf: risk-free rate
        :param pd.DataFrame data: NAV series, so that you can also use this backtester after some other Python programs
        without loading a local Excel file
        """
        self.ann = ann
        self.rf = rf
        self.input_path = self.output_path = None
        self.data = data
        self.backtest_results = dict()

    def load_sheet_from_file(self, input_path: str, sheet_name='Sheet1'):
        """
        Load NAV series data from a local Excel file
        :param str input_path: file path of the Excel file
        :param str sheet_name: name of the sheet containing NAV series, 'Sheet1' by default
        """
        self.input_path = input_path
        self.data = pd.read_excel(self.input_path, sheet_name=sheet_name, index_col=0)

    def slice(self, start_date=None, end_date=None):
        """
        Slice the NAV series data based on desired start and end
        :param str start_date: desired start date
        :param str end_date: desired end date
        """
        self.data = self.data.loc[pd.to_datetime(start_date):pd.to_datetime(end_date)]

    def backtest_series(self, nav_series: pd.Series, annualize: bool):
        """
        Backtest the given NAV series, regardless of its length
        So that this method can be used to both backtest the entire period, as well as backtest by year as long as nav_series is properly sliced
        :param pd.Series nav_series: nav series used to calculate stats
        :param bool annualize: whether return is annualized
        :return pd.DataFrame: a DataFrame of stats
        """
        ret_series = nav_series.pct_change()

        # --------------------------------------------------------------------------------------------------------------
        # Calculate return and stdev
        holding_period_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
        annualized_return = (holding_period_return + 1) ** (self.ann / (len(ret_series) - 1)) - 1 if annualize is True else holding_period_return
        # should take ((len(ret_series) - 1) / self.ann)-th root of HPR, i.e. raise it to the (self.ann / (len(ret_series) - 1))-th power
        # len(ret_series) needs to minus 1 because of the initial np.nan as a result of pct_change()
        annualized_stdev = np.nanstd(ret_series, ddof=1) * np.sqrt(self.ann)

        # --------------------------------------------------------------------------------------------------------------
        # Calculate mdd and ratios
        mdd, mdd_start, mdd_formation = self.mdd(nav_series)

        sharpe, calmar = (annualized_return - self.rf) / annualized_stdev, (annualized_return - self.rf) / mdd

        # --------------------------------------------------------------------------------------------------------------
        # Store results to the dataframe
        df = pd.DataFrame(
            {'区间收益率': [holding_period_return], '年化收益率': [annualized_return],
             '年化波动率': [annualized_stdev], '最大回撤': [mdd], '夏普比率': [sharpe], '卡玛比率': [calmar],
             '最大回撤起始时间': [mdd_start], '最大回撤形成时间': [mdd_formation], '最大回撤恢复时间': [np.nan]
             })

        return df

    def backtest(self, asset_name: str):
        """
        Run backtest on the selected asset
        :param str asset_name: name of the asset, used to locate the column among many assets
        """
        if asset_name not in self.data.columns:
            raise ValueError('invalid asset name')
        nav_series = self.data[asset_name].dropna()
        df_list = []

        # --------------------------------------------------------------------------------------------------------------
        # Backtest the entire period
        df_all = self.backtest_series(nav_series, annualize=True)
        try:
            df_all['最大回撤恢复时间'] = nav_series.loc[(nav_series >= nav_series.loc[df_all['最大回撤起始时间']][0]) & (pd.to_datetime(nav_series.index) > pd.to_datetime(df_all['最大回撤起始时间'][0]))].index[0].date()
        except:
            df_all['最大回撤恢复时间'] = '尚未恢复'
        df_all.index = ['整体表现']
        df_list.append(df_all)

        # --------------------------------------------------------------------------------------------------------------
        # Backtest by year
        years = list(set(nav_series.index.year))
        years.sort()
        for idx, year in enumerate(years):
            nav_series_by_year = nav_series.loc[nav_series.index.year == year]
            if idx == 0:
                # if the first year only involves one data point, it merely serves as the opening price of the next year's series
                if len(nav_series_by_year) == 1:
                    continue
            else:
                last_year_close = pd.Series([nav_series.loc[nav_series.index.year == years[idx - 1]].iloc[-1]])
                last_year_close.index = [nav_series.loc[nav_series.index.year == years[idx - 1]].index[-1]]
                last_year_close.name = nav_series_by_year.name
                nav_series_by_year = last_year_close.append(nav_series_by_year)
            df_by_year = self.backtest_series(nav_series_by_year, annualize=False)
            try:
                df_by_year['最大回撤恢复时间'] = nav_series.loc[
                    (nav_series >= nav_series.loc[df_by_year['最大回撤起始时间']][0]) & (pd.to_datetime(nav_series.index) > pd.to_datetime(df_by_year['最大回撤起始时间'][0]))].index[0].date()
            except:
                df_by_year['最大回撤恢复时间'] = '尚未恢复'
            df_by_year.index = [year]
            df_list.append(df_by_year)

        # --------------------------------------------------------------------------------------------------------------
        # Concatenate results to get one holistic DataFrame
        df = pd.concat(df_list)
        self.backtest_results[asset_name] = df

    def mdd(self, nav_series):
        """
        Calculate maximum drawdown using the given NAV series
        :param pd.Series nav_series: NAV series used to calculate mdd stats
        :return : stats
        """
        dd = nav_series.div(nav_series.cummax()).sub(1)
        # NAV divided by its cumulative maximum then subtracted by 1 gives the drawdown series
        mdd, formation = dd.min(), dd.idxmin()
        formation = formation.date()
        start = nav_series.loc[:formation].idxmax()
        start = start.date()
        return -mdd, start, formation

    def output(self, output_path: str, asset_name_list: list):
        """
        Save results as an Excel file
        :param str output_path: desired file path of the Excel file containing backtest results
        :param list asset_name_list: list of names of assets whose backtest results are to be output
        """
        writer = pd.ExcelWriter(output_path, engine='xlsxwriter')
        for asset in asset_name_list:
            if asset not in self.backtest_results.keys():
                print('invalid asset %s, either no data or hasn\'t been backtested.' % asset)
            else:
                self.backtest_results[asset].to_excel(writer, sheet_name=asset)
        writer.save()


if __name__ == '__main__':
    a = Single_Asset(ann=250, rf=0)
    a.load_sheet_from_file(r'E:\College\Gap\Huatai\Backtesting-Toolkit\Data\data.xlsx', sheet_name='数据')
    #start_date = "2000-12-01"
    #end_date = "2020-12-31"
    #a.slice(start_date, end_date)
    a.backtest('沪深300')
    a.backtest('中证500')
    a.output(output_path=r'E:\College\Gap\Huatai\Backtesting-Toolkit\输出\回测结果.xlsx', asset_name_list=['沪深300', '中证500'])