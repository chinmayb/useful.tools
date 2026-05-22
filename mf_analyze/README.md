# Mutual Fund Portfolio Analyzer

A comprehensive tool for analyzing mutual fund portfolios with Zerodha integration and advanced visualization capabilities.

## 🚀 Features

- **Portfolio Analysis**: Complete performance metrics and returns calculation
- **Risk Assessment**: Volatility, VaR, and risk-adjusted returns
- **Asset Allocation**: Visual breakdown by categories and funds
- **Benchmark Comparison**: Compare against NIFTY, Sensex, and other indices
- **Zerodha Integration**: Fetch real portfolio data using MCP integration
- **Interactive Visualizations**: Charts and graphs for better insights
- **Export Capabilities**: Save analysis to Excel and CSV formats

## 📁 Project Structure

```
mf_analyze/
├── mf_analyzer.py          # Main portfolio analysis class
├── zerodha_integration.py  # Zerodha API integration
├── MF_Portfolio_Analysis.ipynb  # Interactive Jupyter notebook
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## 🛠️ Installation

1. **Clone or download this project**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up Zerodha credentials** (optional for real data):
   - Get API key and secret from Zerodha Console
   - Configure MCP Zerodha integration

## 📊 Usage

### Quick Start with Sample Data

```python
from mf_analyzer import MFPortfolioAnalyzer

# Initialize analyzer
analyzer = MFPortfolioAnalyzer()

# Load sample data
holdings = analyzer.load_sample_data()

# Get portfolio summary
summary = analyzer.get_portfolio_summary()
print(summary)

# Generate visualizations
analyzer.plot_portfolio_allocation()
analyzer.plot_performance_chart()
```

### Using Jupyter Notebook (Recommended)

1. **Start Jupyter**:
   ```bash
   jupyter notebook
   ```

2. **Open**: `MF_Portfolio_Analysis.ipynb`

3. **Run all cells** to see complete analysis

### With Real Zerodha Data

```python
from zerodha_integration import ZerodhaMFIntegration

# Connect to Zerodha
zerodha = ZerodhaMFIntegration()
if zerodha.connect_zerodha():
    holdings = zerodha.fetch_mf_holdings()
```

## 📈 Available Analysis

### Portfolio Metrics
- Total invested amount and current value
- Absolute and percentage returns
- Risk-adjusted performance metrics
- Top and bottom performers

### Risk Analysis
- Portfolio volatility
- Value at Risk (VaR)
- Return distribution analysis
- Risk-return scatter plots

### Asset Allocation
- Category-wise breakdown
- Fund-wise allocation
- Investment vs current value comparison
- Diversification analysis

### Benchmark Comparison
- Performance vs NIFTY 50, Sensex, etc.
- Risk-adjusted comparison
- Cumulative return analysis

## 🔗 Zerodha MCP Integration

This project supports integration with Zerodha through Model Context Protocol (MCP). Available functions:

- `mcp_zerodha-mcp_login()`: Login to Kite API
- `mcp_zerodha-mcp_get_mf_holdings()`: Fetch mutual fund holdings
- `mcp_zerodha-mcp_get_profile()`: Get user profile
- `mcp_zerodha-mcp_get_positions()`: Get current positions

### Setup Instructions
1. Ensure you have Zerodha API credentials
2. Use the MCP tools to authenticate
3. The system will guide you through the process

## 📋 Sample Output

```
📊 Portfolio Holdings:
                               scheme_name      isin  current_value  ...
0    SBI Small Cap Fund-Direct Plan-Growth  INF200K01VK5     125000  ...
1     Axis Bluechip Fund-Direct Plan-Growth  INF846K01EW2     180000  ...

💰 Portfolio Performance Summary:
========================================
Total Invested: ₹560,000.00
Current Value: ₹650,000.00
Absolute Returns: ₹90,000.00
Overall Return %: 16.07%
Number of Funds: 5
```

## 📊 Export Options

- **Excel Report**: Complete analysis with multiple sheets
- **CSV Data**: Raw portfolio data
- **Chart Images**: Save visualizations for presentations

```python
# Export to Excel
analyzer.export_analysis('my_portfolio_analysis.xlsx')

# Export to CSV
zerodha.export_to_csv('portfolio_data.csv')
```

## 🛡️ Risk Disclaimer

This tool is for educational and analysis purposes only. It does not provide investment advice. Always consult with a qualified financial advisor before making investment decisions.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📝 License

This project is open source. Feel free to use and modify as needed.

## 🔧 Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all dependencies are installed
   ```bash
   pip install -r requirements.txt
   ```

2. **Zerodha Connection**: Check API credentials and network connection

3. **Visualization Issues**: Install matplotlib and seaborn
   ```bash
   pip install matplotlib seaborn
   ```

## 📞 Support

For issues or questions:
1. Check the troubleshooting section
2. Review the sample code in the notebook
3. Ensure all dependencies are properly installed

---

**Happy Investing! 📈💰**
