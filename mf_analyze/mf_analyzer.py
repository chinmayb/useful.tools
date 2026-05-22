import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

class MFPortfolioAnalyzer:
    """
    Mutual Fund Portfolio Analysis Tool
    """
    
    def __init__(self):
        self.holdings = None
        self.performance_data = {}
        
    def load_sample_data(self):
        """Load sample MF portfolio data for demonstration.

        Uses real AMFI scheme codes and ISINs (verified against the AMFI master at
        data/amfi_scheme_master.csv). NAV/units are illustrative, not live.
        """
        sample_data = {
            'scheme_code': ['125497', '120465', '119063', '118825', '122639'],
            'scheme_name': [
                'SBI Small Cap Fund - Direct Plan - Growth',
                'Axis Large Cap Fund - Direct Plan - Growth',
                'HDFC Nifty 50 Index Fund - Direct Plan',
                'Mirae Asset Large Cap Fund - Direct Plan - Growth',
                'Parag Parikh Flexi Cap Fund - Direct Plan - Growth',
            ],
            'isin': [
                'INF200K01T51',
                'INF846K01DP8',
                'INF179K01WM1',
                'INF769K01AX2',
                'INF879O01027',
            ],
            'current_value': [125000, 180000, 95000, 110000, 140000],
            'invested_amount': [100000, 150000, 90000, 100000, 120000],
            'units': [651.86, 3450.12, 1842.95, 898.21, 1544.78],
            'avg_cost': [153.41, 43.48, 48.83, 111.34, 77.68],
            'current_nav': [191.76, 51.83, 51.55, 122.41, 90.61],
            'category': ['Small Cap', 'Large Cap', 'Index Funds', 'Large Cap', 'Flexi Cap'],
        }
        
        self.holdings = pd.DataFrame(sample_data)
        
        # Calculate additional metrics
        self.holdings['absolute_return'] = self.holdings['current_value'] - self.holdings['invested_amount']
        self.holdings['return_percentage'] = (self.holdings['absolute_return'] / self.holdings['invested_amount']) * 100
        
        print("✅ Sample MF portfolio data loaded successfully!")
        return self.holdings
        
    def get_portfolio_summary(self):
        """Get overall portfolio summary"""
        if self.holdings is None:
            print("❌ No portfolio data found. Please load data first.")
            return None
            
        total_invested = self.holdings['invested_amount'].sum()
        total_current = self.holdings['current_value'].sum()
        total_returns = total_current - total_invested
        overall_return_pct = (total_returns / total_invested) * 100
        
        summary = {
            'Total Invested': f"₹{total_invested:,.2f}",
            'Current Value': f"₹{total_current:,.2f}",
            'Absolute Returns': f"₹{total_returns:,.2f}",
            'Overall Return %': f"{overall_return_pct:.2f}%",
            'Number of Funds': len(self.holdings)
        }
        
        return summary
        
    def analyze_allocation(self):
        """Analyze portfolio allocation by category"""
        if self.holdings is None:
            return None
            
        allocation = self.holdings.groupby('category')['current_value'].agg(['sum', 'count'])
        allocation['percentage'] = (allocation['sum'] / allocation['sum'].sum()) * 100
        allocation.columns = ['Total Value', 'Number of Funds', 'Allocation %']
        
        return allocation
        
    def plot_portfolio_allocation(self):
        """Create portfolio allocation pie chart"""
        if self.holdings is None:
            return None
            
        plt.figure(figsize=(10, 6))
        
        # Allocation by category
        plt.subplot(1, 2, 1)
        category_allocation = self.holdings.groupby('category')['current_value'].sum()
        plt.pie(category_allocation.values, labels=category_allocation.index, autopct='%1.1f%%')
        plt.title('Portfolio Allocation by Category')
        
        # Top funds by value
        plt.subplot(1, 2, 2)
        top_funds = self.holdings.nlargest(5, 'current_value')
        plt.pie(top_funds['current_value'], labels=top_funds['scheme_name'].str[:20], autopct='%1.1f%%')
        plt.title('Top 5 Funds by Value')
        
        plt.tight_layout()
        plt.show()
        
    def plot_performance_chart(self):
        """Create performance visualization"""
        if self.holdings is None:
            return None
            
        plt.figure(figsize=(12, 8))
        
        # Returns by fund
        plt.subplot(2, 2, 1)
        funds = self.holdings['scheme_name'].str[:15]  # Truncate names
        returns = self.holdings['return_percentage']
        colors = ['green' if r > 0 else 'red' for r in returns]
        plt.bar(range(len(funds)), returns, color=colors, alpha=0.7)
        plt.title('Returns by Fund (%)')
        plt.xticks(range(len(funds)), funds, rotation=45, ha='right')
        plt.ylabel('Return %')
        
        # Investment vs Current Value
        plt.subplot(2, 2, 2)
        x = np.arange(len(funds))
        width = 0.35
        plt.bar(x - width/2, self.holdings['invested_amount']/1000, width, label='Invested', alpha=0.7)
        plt.bar(x + width/2, self.holdings['current_value']/1000, width, label='Current', alpha=0.7)
        plt.title('Invested vs Current Value (₹000s)')
        plt.xticks(x, funds, rotation=45, ha='right')
        plt.legend()
        
        # Portfolio composition
        plt.subplot(2, 2, 3)
        category_allocation = self.holdings.groupby('category')['current_value'].sum()
        plt.pie(category_allocation.values, labels=category_allocation.index, autopct='%1.1f%%')
        plt.title('Asset Allocation')
        
        # Performance distribution
        plt.subplot(2, 2, 4)
        plt.hist(self.holdings['return_percentage'], bins=10, alpha=0.7, edgecolor='black')
        plt.title('Return Distribution')
        plt.xlabel('Return %')
        plt.ylabel('Number of Funds')
        
        plt.tight_layout()
        plt.show()
        
    def get_top_performers(self, n=3):
        """Get top performing funds"""
        if self.holdings is None:
            return None
            
        top_performers = self.holdings.nlargest(n, 'return_percentage')[
            ['scheme_name', 'return_percentage', 'absolute_return', 'current_value']
        ]
        
        return top_performers
        
    def get_underperformers(self, n=3):
        """Get underperforming funds"""
        if self.holdings is None:
            return None
            
        underperformers = self.holdings.nsmallest(n, 'return_percentage')[
            ['scheme_name', 'return_percentage', 'absolute_return', 'current_value']
        ]
        
        return underperformers
        
    def export_analysis(self, filename='mf_portfolio_analysis.xlsx'):
        """Export analysis to Excel file"""
        if self.holdings is None:
            return None
            
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            # Holdings details
            self.holdings.to_excel(writer, sheet_name='Holdings', index=False)
            
            # Summary
            summary_df = pd.DataFrame(list(self.get_portfolio_summary().items()), 
                                    columns=['Metric', 'Value'])
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Allocation
            allocation_df = self.analyze_allocation()
            allocation_df.to_excel(writer, sheet_name='Allocation')
            
        print(f"✅ Analysis exported to {filename}")

# Example usage
if __name__ == "__main__":
    analyzer = MFPortfolioAnalyzer()
    
    # Load sample data
    holdings = analyzer.load_sample_data()
    print("\n📊 Portfolio Holdings:")
    print(holdings.to_string(index=False))
    
    # Get summary
    print("\n📈 Portfolio Summary:")
    summary = analyzer.get_portfolio_summary()
    for key, value in summary.items():
        print(f"{key}: {value}")
    
    # Show allocation
    print("\n🎯 Asset Allocation:")
    allocation = analyzer.analyze_allocation()
    print(allocation)
    
    # Top performers
    print("\n🏆 Top Performers:")
    top = analyzer.get_top_performers()
    print(top.to_string(index=False))
    
    # Underperformers  
    print("\n⚠️ Underperformers:")
    under = analyzer.get_underperformers()
    print(under.to_string(index=False))
