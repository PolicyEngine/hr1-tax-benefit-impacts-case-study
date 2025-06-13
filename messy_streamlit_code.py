"""
HR1 Tax Bill - Household Impact Dashboard

A Streamlit application for analyzing the impact of the HR1 tax bill on individual households.
Provides interactive filtering, analysis type selection, and detailed impact visualization.
"""

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnalysisType(Enum):
    """Supported analysis focus types for the dashboard."""
    FEDERAL_TAXES = "Federal Taxes"
    NET_INCOME = "Net Income"
    STATE_TAXES = "State Taxes"


class AppConfig:
    """Application-wide configuration constants."""
    CSV_FILENAME = "household_tax_income_changes.csv"
    INCOME_CHANGE_THRESHOLD = 0.01
    SIGNIFICANT_IMPACT_THRESHOLD = 1000
    MODERATE_IMPACT_THRESHOLD = 100
    MAX_DEPENDENTS = 11  # Based on IRS maximum dependent limit for tax modeling
    CHART_HEIGHT = 500

    # Reform column mappings: (Display Name, Column Suffix)
    REFORM_COLS = [
        ("Tax Rate Reform", "Tax Rate Reform"),
        ("Standard Deduction Reform", "Standard Deduction Reform"),
        ("Exemption Reform", "Exemption Reform"),
        ("Child Tax Credit Reform", "CTC Reform"),
        ("QBID Reform", "QBID Reform"),
        ("AMT Reform", "AMT Reform"),
        ("SALT Reform", "SALT Reform"),
        ("Estate Tax Reform", "Estate Tax Reform"),
        ("Tip Income Exemption", "Tip Income Exempt"),
        ("Senior Deduction Reform", "Senior Deduction Reform"),
        ("Overtime Income Exemption", "Overtime Income Exempt"),
        ("Auto Loan Interest Deduction", "Auto Loan Interest ALD"),
        ("Miscellaneous Reform", "Miscellaneous Reform"),
        ("Limitation on Itemized Deductions", "Other Itemized Deductions Reform"),
        ("Pease Reform", "Pease Reform")
    ]

    # Income source mappings for display
    INCOME_SOURCES = [
        ("Employment Income", "Employment Income"),
        ("Self-Employment Income", "Self-Employment Income"),
        ("Tip Income", "Tip Income"),
        ("Overtime Income", "Overtime Income"),
        ("Capital Gains", "Capital Gains")
    ]


class UIConfig:
    """UI styling and configuration constants."""
    CONTAINER_STYLE = "padding: 10px; border-radius: 5px; background-color: #f0f2f6;"

@dataclass
class FilterConfig:
    """Configuration for data filtering options."""
    weight_options: Dict[str, int]
    income_ranges: Dict[str, Tuple[float, float]]
    age_ranges: Dict[str, Tuple[int, int]]
    dependent_options: List[str]
    marital_options: List[str]
    single_tax_unit: bool

    @classmethod
    def default(cls) -> 'FilterConfig':
        """Create default filter configuration."""
        return cls(
            weight_options={
                "All Households": 0,
                "Weight 1,000+": 1000,
                "Weight 5,000+": 5000,
                "Weight 10,000+": 10000,
                "Weight 25,000+": 25000,
                "Weight 50,000+": 50000
            },
            income_ranges={
                "All Income Levels": (0, float('inf')),
                "Under $25k": (0, 25000),
                "$25k - $50k": (25000, 50000),
                "$50k - $100k": (50000, 100000),
                "$100k - $200k": (100000, 200000),
                "$200k+": (200000, float('inf'))
            },
            age_ranges={
                "All Ages": (0, 200),
                "Under 30": (0, 30),
                "30-40": (30, 40),
                "40-50": (40, 50),
                "50-60": (50, 60),
                "60-70": (60, 70),
                "70-80": (70, 80),
                "80+": (80, 200)
            },
            dependent_options=["All", "0", "1", "2", "3+"],
            marital_options=["All", "Married", "Single"],
            single_tax_unit=False
        )


@dataclass
class ReformImpact:
    """Represents the financial impact of a single tax reform."""
    name: str
    total_change: float
    
    @property
    def is_significant(self) -> bool:
        """Check if the reform impact is significant enough to display."""
        return abs(self.total_change) > AppConfig.INCOME_CHANGE_THRESHOLD


@dataclass
class HouseholdProfile:
    """Demographic and financial profile of a household."""
    household_id: int
    state: str
    age_of_head: float
    age_of_spouse: Optional[float]
    number_of_dependents: int
    is_married: bool
    baseline_federal_tax: float
    baseline_net_income: float
    household_weight: float
    
    @classmethod
    def from_series(cls, series: pd.Series) -> 'HouseholdProfile':
        """Create a HouseholdProfile from a pandas Series."""
        return cls(
            household_id=int(series['Household ID']),
            state=series['State'],
            age_of_head=series['Age of Head'],
            age_of_spouse=series.get('Age of Spouse'),
            number_of_dependents=int(series['Number of Dependents']),
            is_married=bool(series['Is Married']),
            baseline_federal_tax=series['Baseline Federal Tax Liability'],
            baseline_net_income=series['Baseline Net Income'],
            household_weight=series['Household Weight']
        )


class DataManager:
    """Handles data loading, validation, and caching."""
    
    @staticmethod
    @st.cache_data
    def load_data() -> pd.DataFrame:
        """
        Load and validate household data from CSV file.
        
        Returns:
            pd.DataFrame: Validated household data
            
        Raises:
            FileNotFoundError: If CSV file is not found
            ValueError: If required columns are missing
        """
        try:
            df = pd.read_csv(AppConfig.CSV_FILENAME)
            DataManager._validate_data(df)
            logger.info(f"Successfully loaded {len(df)} household records")
            return df
        except FileNotFoundError:
            st.error(f"Data file {AppConfig.CSV_FILENAME} not found")
            st.stop()
        except Exception as e:
            st.error(f"Error loading data: {str(e)}")
            st.stop()
    
    @staticmethod
    def _validate_data(df: pd.DataFrame) -> None:
        """Validate that all required columns exist in the dataframe."""
        required_columns = [
            'Household ID', 'State', 'Age of Head', 'Number of Dependents',
            'Is Married', 'Baseline Federal Tax Liability', 'Baseline Net Income',
            'Household Weight', 'Total Change in Federal Tax Liability',
            'Total Change in Net Income'
        ]
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")


class FilterManager:
    """Manages data filtering operations and UI rendering."""
    
    def __init__(self, config: FilterConfig):
        """Initialize with filter configuration."""
        self.config = config
    
    def render_and_apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Render filter UI in sidebar and apply selected filters to dataframe.
        
        Args:
            df: Original dataframe to filter
            
        Returns:
            pd.DataFrame: Filtered dataframe based on user selections
        """
        with st.sidebar.expander("🔍 Filters"):
            df_filtered = df.copy()
            
            # Apply each filter sequentially
            filter_methods = [
                self._apply_weight_filter,
                self._apply_income_filter,
                lambda x: self._apply_state_filter(x, df),
                self._apply_marital_filter,
                self._apply_dependents_filter,
                self._apply_age_filter,
                self._apply_tax_unit_filter
            ]
            
            for filter_method in filter_methods:
                df_filtered = filter_method(df_filtered)
            
            self._display_filter_results(df_filtered, df)
            
        return df_filtered
    
    def _apply_weight_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply household weight filter."""
        selected = st.selectbox("Minimum Household Weight:", list(self.config.weight_options.keys()))
        min_weight = self.config.weight_options[selected]
        return df[df['Household Weight'] >= min_weight] if min_weight > 0 else df
    
    def _apply_income_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply income range filter."""
        selected = st.selectbox("Net Income:", list(self.config.income_ranges.keys()))
        min_income, max_income = self.config.income_ranges[selected]
        if min_income > 0 or max_income < float('inf'):
            return df[(df['Baseline Net Income'] >= min_income) & 
                     (df['Baseline Net Income'] <= max_income)]
        return df
    
    def _apply_state_filter(self, df_filtered: pd.DataFrame, df_original: pd.DataFrame) -> pd.DataFrame:
        """Apply state filter."""
        states = ["All States"] + sorted(df_original['State'].unique().tolist())
        selected = st.selectbox("State:", states)
        return df_filtered[df_filtered['State'] == selected] if selected != "All States" else df_filtered
    
    def _apply_marital_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply marital status filter."""
        selected = st.selectbox("Marital Status:", self.config.marital_options)
        if selected != "All":
            is_married = selected == "Married"
            return df[df['Is Married'] == is_married]
        return df
    
    def _apply_dependents_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply number of dependents filter."""
        selected = st.selectbox("Number of Dependents:", self.config.dependent_options)
        if selected != "All":
            if selected == "3+":
                return df[df['Number of Dependents'] >= 3]
            else:
                return df[df['Number of Dependents'] == int(selected)]
        return df
    
    def _apply_age_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply head of household age filter."""
        selected = st.selectbox("Head of Household Age:", list(self.config.age_ranges.keys()))
        min_age, max_age = self.config.age_ranges[selected]
        if selected != "All Ages":
            return df[(df['Age of Head'] >= min_age) & (df['Age of Head'] < max_age)]
        return df
        
    def _apply_tax_unit_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply tax unit filter."""
        selected = st.checkbox("Households with Only 1 Tax Unit", value=self.config.single_tax_unit)
        if selected:
            return df[df['Number of Tax Units'] == 1]
        return df
    
    def _display_filter_results(self, df_filtered: pd.DataFrame, df_original: pd.DataFrame) -> None:
        """Display filter results summary."""
        st.caption(f"📊 Showing {len(df_filtered):,} of {len(df_original):,} households")
        if len(df_filtered) == 0:
            st.error("No households match your filters!")
            st.stop()


class HouseholdSelector:
    """Handles household selection methods and UI."""
    
    @staticmethod
    def select_household(df_filtered: pd.DataFrame) -> int:
        """
        Render household selection UI and return selected household ID.
        
        Args:
            df_filtered: Filtered dataframe to select from
            
        Returns:
            int: Selected household ID
        """
        selection_method = st.sidebar.radio(
            "Selection Method:",
            ["Random Shuffle", "By Household ID", "Find Interesting Cases"]
        )
        
        selection_methods = {
            "By Household ID": HouseholdSelector._select_by_id,
            "Random Shuffle": HouseholdSelector._select_random,
            "Find Interesting Cases": HouseholdSelector._select_interesting_case
        }
        
        return selection_methods[selection_method](df_filtered)
    
    @staticmethod
    def _select_by_id(df_filtered: pd.DataFrame) -> int:
        """Select household by ID."""
        return int(st.sidebar.selectbox("Choose Household ID:", df_filtered['Household ID'].unique()))
    
    @staticmethod
    def _select_random(df_filtered: pd.DataFrame) -> int:
        """Select random household with button to reshuffle, biased towards higher weights."""
        if st.sidebar.button("🎲 Get Random Household"):
            # Use household weight as sampling probability
            st.session_state.random_household = df_filtered.sample(1, weights='Household Weight')['Household ID'].iloc[0]
        
        if 'random_household' not in st.session_state:
            st.session_state.random_household = df_filtered.sample(1, weights='Household Weight')['Household ID'].iloc[0]
        
        household_id = st.session_state.random_household
        st.sidebar.info(f"Random Household ID: {household_id}")
        return int(household_id)
    
    @staticmethod
    def _select_interesting_case(df_filtered: pd.DataFrame) -> int:
        """Select household from interesting cases (highest/lowest impacts)."""
        case_configs = {
            "Largest % Federal Tax Increase": ('nlargest', 'Percentage Change in Federal Tax Liability'),
            "Largest % Federal Tax Decrease": ('nsmallest', 'Percentage Change in Federal Tax Liability'),
            "Largest Federal Tax Increase": ('nlargest', 'Total Change in Federal Tax Liability'),
            "Largest Federal Tax Decrease": ('nsmallest', 'Total Change in Federal Tax Liability'),
            "Largest % Income Increase": ('nlargest', 'Percentage Change in Net Income'),
            "Largest % Income Decrease": ('nsmallest', 'Percentage Change in Net Income'),
            "Largest Income Increase": ('nlargest', 'Total Change in Net Income'),
            "Largest Income Decrease": ('nsmallest', 'Total Change in Net Income')
        }
        
        case_type = st.sidebar.selectbox("Select Case Type:", list(case_configs.keys()))
        method, column = case_configs[case_type]
        
        try:
            top_households = getattr(df_filtered, method)(20, column)
            ranked_options, household_ids = HouseholdSelector._create_ranked_options(top_households, case_type)
            
            selected_option = st.sidebar.selectbox(f"Top 20 for {case_type}:", ranked_options)
            selected_index = ranked_options.index(selected_option)
            household_id = household_ids[selected_index]
            
            st.sidebar.info(f"Selected Household ID: {household_id}")
            return int(household_id)
        except Exception as e:
            logger.error(f"Error retrieving interesting cases: {str(e)}")
            st.error("Error retrieving households. Please try different filters.")
            st.stop()
    
    @staticmethod
    def _create_ranked_options(top_households: pd.DataFrame, case_type: str) -> Tuple[List[str], List[int]]:
        """Create ranked options for interesting case selection."""
        ranked_options, household_ids = [], []
        
        for i, (_, row) in enumerate(top_households.iterrows(), 1):
            household_ids.append(row['Household ID'])
            
            if "%" in case_type:
                column = 'Percentage Change in Federal Tax Liability' if "Tax" in case_type else 'Percentage Change in Net Income'
                value = row[column]
                ranked_options.append(f"#{i}: {value:+.1f}%")
            else:
                column = 'Total Change in Federal Tax Liability' if "Tax" in case_type else 'Total Change in Net Income'
                value = row[column]
                ranked_options.append(f"#{i}: ${value:+,.0f}")
        
        return ranked_options, household_ids


class TaxAnalysisEngine:
    """Unified tax analysis engine that handles all analysis types."""
    
    def __init__(self, analysis_type: AnalysisType):
        """Initialize with specific analysis type."""
        self.analysis_type = analysis_type
    
    def get_reform_impacts(self, household_data: pd.Series) -> List[ReformImpact]:
        """
        Calculate reform impacts for the specific analysis type.
        
        Args:
            household_data: Household data series
            
        Returns:
            List[ReformImpact]: List of significant reform impacts
        """
        impacts = []
        column_prefix = self._get_column_prefix()
        
        for display_name, col_name in AppConfig.REFORM_COLS:
            try:
                change_value = household_data[f'{column_prefix} {col_name}']
                impact = ReformImpact(name=display_name, total_change=change_value)
                
                if impact.is_significant:
                    impacts.append(impact)
            except KeyError:
                continue
        
        return impacts
    
    def get_chart_title(self) -> str:
        """Get the appropriate chart title for the analysis type."""
        titles = {
            AnalysisType.FEDERAL_TAXES: "Federal Tax Liability",
            AnalysisType.STATE_TAXES: "State Tax Liability", 
            AnalysisType.NET_INCOME: "Net Income"
        }
        return titles[self.analysis_type]
    
    def get_baseline_info(self, profile: HouseholdProfile, household_data: pd.Series) -> Tuple[float, str]:
        """
        Get baseline value and label for the analysis type.
        
        Returns:
            Tuple[float, str]: (baseline_value, baseline_label)
        """
        mapping = {
            AnalysisType.FEDERAL_TAXES: (profile.baseline_federal_tax, "Federal Taxes"),
            AnalysisType.STATE_TAXES: (household_data.get('State Income Tax', 0), "State Taxes"),
            AnalysisType.NET_INCOME: (profile.baseline_net_income, "Net Income")
        }
        return mapping[self.analysis_type]
    
    def get_change_info(self, household_data: pd.Series) -> Tuple[float, float, str, str, float]:
        """
        Get change information for impact summary. Helps to calculate post-reform value, too.
        
        Returns:
            Tuple[float, float, str, str, float]: (change_value, pct_change, change_label, color, final_value)
        """
        mapping = {
            AnalysisType.FEDERAL_TAXES: (
                household_data['Total Change in Federal Tax Liability'],
                household_data['Percentage Change in Federal Tax Liability'],
                "Federal Tax Change",
                household_data['Baseline Federal Tax Liability'], "Reformed Federal Tax"
            ),
            AnalysisType.STATE_TAXES: (
                household_data['Total Change in State Tax Liability'],
                household_data['Percentage Change in State Tax Liability'],
                "State Tax Change",
                household_data.get('State Income Tax', 0), "Reformed State Tax"
            ),
            AnalysisType.NET_INCOME: (
                household_data['Total Change in Net Income'],
                household_data['Percentage Change in Net Income'],
                "Net Income Change",
                household_data['Baseline Net Income'], "Reformed Net Income"
            )
        }
        
        change_value, pct_change, change_label, baseline_value, final_label = mapping[self.analysis_type]
        final_value = baseline_value + change_value
        
        # Determine color based on analysis type and value
        if self.analysis_type == AnalysisType.NET_INCOME:
            color = "green" if change_value > 0 else "red"  # Income increase is good
        else:
            color = "red" if change_value > 0 else "green"  # Tax increase is bad
            
        return change_value, pct_change, change_label, final_label, color, final_value
    
    def _get_column_prefix(self) -> str:
        """Get the column prefix for reform impact columns."""
        prefixes = {
            AnalysisType.FEDERAL_TAXES: "Change in Federal tax liability after",
            AnalysisType.STATE_TAXES: "Change in State tax liability after",
            AnalysisType.NET_INCOME: "Change in Net income after"
        }
        return prefixes[self.analysis_type]


class VisualizationRenderer:
    """Handles all UI rendering operations with consistent styling."""
    
    def __init__(self, analysis_engine: TaxAnalysisEngine):
        """Initialize with analysis engine."""
        self.analysis_engine = analysis_engine
    
    def render_main_content(self, profile: HouseholdProfile, household_data: pd.Series) -> None:
        """Render the main dashboard content in two columns."""
        col1, col2 = st.columns(2)
        
        with col1:
            self._render_household_attributes(profile, household_data)
            self._render_weight_info(household_data)
        
        with col2:
            self._render_baseline_info(profile, household_data)
            self._render_impact_summary(household_data)
        
        # Render analysis sections
        impacts = self.analysis_engine.get_reform_impacts(household_data)
        self._render_reform_breakdown(impacts)
        
        if impacts:
            self._render_waterfall_chart(impacts, household_data)
        else:
            st.info("This household is not significantly affected by any specific reform components.")
    
    def _render_styled_container(self, title: str, content: str) -> None:
        """Helper method to render consistently styled containers."""
        st.markdown(f"""
        <div style="{UIConfig.CONTAINER_STYLE}">
        <h4>{title}</h4>
        {content}
        </div>
        """, unsafe_allow_html=True)
    
    def _build_household_attributes_content(self, profile: HouseholdProfile, household_data: pd.Series) -> str:
        """Build HTML content for household attributes display."""
        # Basic attributes
        attributes = [
            ("State", profile.state),
            ("Number of Tax Units", f"{household_data['Number of Tax Units']:.0f}"),
            ("Head of Household Age", f"{profile.age_of_head:.0f} years"),
            ("Number of Dependents", f"{profile.number_of_dependents:.0f}"),
        ]
        
        content = "".join(f"<p><strong>{label}:</strong> {value}</p>" for label, value in attributes)
        
        # Add children's ages if any
        if profile.number_of_dependents > 0:
            dependent_ages = self._get_dependent_ages(household_data)
            if dependent_ages:
                content += f"<p><strong>Children's Ages:</strong> {', '.join(dependent_ages)} years</p>"
        
        # Add marital status
        marital_info = self._get_marital_info(profile)
        content += f"<p><strong>Marital Status:</strong> {marital_info}</p>"
        
        # Add prominent net income display
        content += f"""<p style='font-size: 20px; font-weight: bold; margin: 15px 0 10px 0;'>
                     <strong> 💰 Net Income:</strong> ${household_data['Baseline Net Income']:,.0f}</p>"""
        
        # Add income sources
        income_content = self._build_income_sources_content(household_data)
        if income_content:
            content += income_content
        
        return content
    
    def _get_dependent_ages(self, household_data: pd.Series) -> List[str]:
        """Extract dependent ages from household data."""
        dependent_ages = []
        for i in range(1, AppConfig.MAX_DEPENDENTS + 1):
            age_col = f'Age of Dependent {i}'
            if age_col in household_data.index:
                age = household_data[age_col]
                if pd.notna(age) and age > 0:
                    dependent_ages.append(f"{age:.0f}")
        return dependent_ages
    
    def _get_marital_info(self, profile: HouseholdProfile) -> str:
        """Get formatted marital status information."""
        if profile.is_married and profile.age_of_spouse:
            return f"Married<br><strong>Spouse Age:</strong> {profile.age_of_spouse:.0f} years"
        else:
            return "Single"
    
    def _build_income_sources_content(self, household_data: pd.Series) -> str:
        """Build HTML content for income sources."""
        income_list = []
        for display_name, column_name in AppConfig.INCOME_SOURCES:
            amount = household_data.get(column_name, 0)
            if amount > 0:
                income_list.append(f"• {display_name}: ${amount:,.0f}")
        
        if income_list:
            content = "<p><strong>Income Sources:</strong></p>"
            content += "".join(f"<p style='margin-left: 10px; margin-top: 2px;'>{income}</p>" 
                             for income in income_list)
            return content
        return ""
    
    def _render_household_attributes(self, profile: HouseholdProfile, household_data: pd.Series) -> None:
        """Render household attributes in a styled container."""
        st.subheader("🏠 Baseline Household Attributes")
        
        content = self._build_household_attributes_content(profile, household_data)
        st.markdown(f"""
        <div style="{UIConfig.CONTAINER_STYLE}">
        {content}
        </div>
        """, unsafe_allow_html=True)

        # Raw data expander outside the styled container
        with st.expander("Full Dataframe Row"):
            st.dataframe(household_data.to_frame().T, use_container_width=True)

    def _render_weight_info(self, household_data: pd.Series) -> None:
        """Render statistical weight information."""
        weight = household_data['Household Weight']
        st.subheader("📈 Statistical Weight")
        with st.container():
            st.metric("Population Weight", f"{math.ceil(weight):,}")
            st.caption("This household represents approximately this many similar households in the U.S.")

    def _render_baseline_info(self, profile: HouseholdProfile, household_data: pd.Series) -> None:
        """Render baseline tax/income information."""
        st.subheader("🔄 HR1 Bill Impact Summary")
        
        baseline_value, baseline_label = self.analysis_engine.get_baseline_info(profile, household_data)
        
        # Build additional taxes content
        additional_content = self._build_additional_taxes_content(profile, household_data)
        
        content = f"<p style='font-size: 18px; font-weight: bold; margin: 0;'>{baseline_label}: ${baseline_value:,.0f}</p>"
        content += additional_content
        
        self._render_styled_container("Baseline Values", content)
        st.markdown("<br>", unsafe_allow_html=True)

    def _build_additional_taxes_content(self, profile: HouseholdProfile, household_data: pd.Series) -> str:
        """Build content for additional taxes section."""
        state_tax = household_data.get('State Income Tax', 0)
        property_tax = household_data.get('Property Taxes', 0)
        
        # Define additional taxes based on analysis type
        tax_mappings = {
            AnalysisType.FEDERAL_TAXES: [
                f"State Taxes: ${state_tax:,.0f}" if state_tax > 0 else None,
                f"Property Taxes: ${property_tax:,.0f}" if property_tax > 0 else None
            ],
            AnalysisType.STATE_TAXES: [
                f"Federal Taxes: ${profile.baseline_federal_tax:,.0f}",
                f"Property Taxes: ${property_tax:,.0f}" if property_tax > 0 else None
            ],
            AnalysisType.NET_INCOME: [
                f"Federal Tax Liability: ${profile.baseline_federal_tax:,.0f}",
                f"State Taxes: ${state_tax:,.0f}" if state_tax > 0 else None,
                f"Property Taxes: ${property_tax:,.0f}" if property_tax > 0 else None
            ]
        }
        
        additional_taxes = [tax for tax in tax_mappings[self.analysis_engine.analysis_type] if tax is not None]
        
        if additional_taxes:
            content = "<p style='margin: 10px 0 0 0;'><strong>Additional Taxes:</strong></p>"
            content += "".join(f"<p style='margin: 2px 0 0 0;'>• {tax}</p>" for tax in additional_taxes)
            return content
        return ""

    def _render_impact_summary(self, household_data: pd.Series) -> None:
        """Render impact summary with appropriate coloring."""
        change_value, pct_change, change_label, final_label, color, final_value = self.analysis_engine.get_change_info(household_data)
        
        content = f"""
        <p style="color: {color}; font-size: 18px; font-weight: bold;">
        {change_label}: ${change_value:,.0f} ({pct_change:+.1f}%)
        </p>
        <p style="font-size: 18px; font-weight: bold; margin-top: 10px;">
        {final_label}: ${final_value:,.0f}
        </p>
        """
        
        self._render_styled_container("Overall Impact", content)
    
    def _render_reform_breakdown(self, impacts: List[ReformImpact]) -> None:
        """Render detailed reform component breakdown."""
        st.subheader("🔍 Detailed Reform Component Analysis")
        
        if not impacts:
            return
            
        cols = st.columns(min(3, len(impacts)))
        for i, impact in enumerate(impacts):
            with cols[i % 3]:
                # Determine label and color based on analysis type
                if self.analysis_engine.analysis_type == AnalysisType.NET_INCOME:
                    label = "Income Change"
                    color = "green" if impact.total_change > 0 else "red"
                else:
                    label = "Tax Change"
                    color = "green" if impact.total_change < 0 else "red"
                
                st.markdown(f"""
                <div style="padding: 8px; border-radius: 5px; background-color: #f9f9f9; margin: 5px 0;">
                <h5>{impact.name}</h5>
                <p style="color: {color}; font-weight: bold;">
                {label}: ${impact.total_change:,.0f}
                </p>
                </div>
                """, unsafe_allow_html=True)
    
    def _render_waterfall_chart(self, impacts: List[ReformImpact], household_data: pd.Series) -> None:
        """Render waterfall chart showing reform impacts."""
        chart_title = self.analysis_engine.get_chart_title()
        st.subheader(f"📊 {chart_title} Impact Waterfall Chart")
        
        try:
            baseline_value, _ = self.analysis_engine.get_baseline_info(
                HouseholdProfile.from_series(household_data), household_data
            )
            
            change_value, _, _, _, _, _ = self.analysis_engine.get_change_info(household_data)
            
            # Prepare waterfall data
            waterfall_data = [(f"Baseline {chart_title}", baseline_value, baseline_value)]
            running_total = baseline_value
            
            for impact in impacts:
                running_total += impact.total_change
                waterfall_data.append((impact.name, impact.total_change, running_total))
            
            final_value = baseline_value + change_value
            waterfall_data.append((f"Final {chart_title}", final_value, final_value))
            
            # Create and display chart
            fig = self._create_waterfall_figure(waterfall_data, chart_title, baseline_value, final_value)
            st.plotly_chart(fig, use_container_width=True)
            
        except Exception as e:
            logger.error(f"Error creating waterfall chart: {str(e)}")
            st.error("Error creating waterfall chart. Please try a different household.")
    
    def _create_waterfall_figure(self, waterfall_data: List[Tuple], chart_title: str, 
                                baseline_value: float, final_value: float) -> go.Figure:
        """Create Plotly waterfall figure."""
        fig = go.Figure()
        
        fig.add_trace(go.Waterfall(
            name=f"{chart_title} Impact",
            orientation="v",
            measure=["absolute"] + ["relative"] * (len(waterfall_data) - 2) + ["total"],
            x=[item[0] for item in waterfall_data],
            y=[item[1] for item in waterfall_data],
            text=[f"${item[1]:,.0f}" for item in waterfall_data],
            textposition="outside",
            connector={"line": {"color": "rgb(63, 63, 63)"}},
            increasing={"marker": {"color": "red"}},
            decreasing={"marker": {"color": "green"}},
            totals={"marker": {"color": "blue"}}
        ))
        
        fig.update_layout(
            title=f"{chart_title} Changes: ${baseline_value:,.0f} → ${final_value:,.0f}",
            xaxis_title="Reform Components",
            yaxis_title=f"{chart_title} ($)",
            showlegend=False,
            height=AppConfig.CHART_HEIGHT,
            xaxis={'tickangle': -45},
            yaxis={'range': [
                min(0, min([item[2] for item in waterfall_data]) * 1.15),
                max(0, max([item[2] for item in waterfall_data]) * 1.15)
            ]})
        
        return fig

    def render_analysis_info_card(self) -> None:
        """Render information card about current analysis scope."""
        st.markdown("---")
        
        # Format reform names list
        reform_names = [display_name for display_name, _ in AppConfig.REFORM_COLS]
        reforms_text = ", ".join(reform_names[:-1]) + f", and {reform_names[-1]}" if len(reform_names) > 1 else reform_names[0]
        
        # Determine analysis focus
        focus_mapping = {
            AnalysisType.FEDERAL_TAXES: "Federal Taxes",
            AnalysisType.NET_INCOME: "Net Income overall",
            AnalysisType.STATE_TAXES: "State Taxes"
        }
        analysis_focus = focus_mapping[self.analysis_engine.analysis_type]
        
        st.info(f"""
        📋 **Analysis Scope:** We are currently analyzing the effects of {reforms_text} on {analysis_focus}.
        """)


class StoryGenerator:
    """Generates journalist-friendly story summaries with proper error handling."""
    
    @staticmethod
    def generate_story_summary(profile: HouseholdProfile, household_data: pd.Series, 
                             impacts: List[ReformImpact]) -> str:
        """
        Generate a story summary for the selected household.
        
        Args:
            profile: Household profile
            household_data: Household data series
            impacts: List of reform impacts
            
        Returns:
            str: Formatted story summary
        """
        try:
            # Extract numeric values with explicit conversion
            income_change = float(household_data['Total Change in Net Income'])
            income_pct_change = float(household_data['Percentage Change in Net Income'])
            household_weight = float(profile.household_weight)
            
            # Determine impact level
            abs_change = abs(income_change)
            if abs_change > AppConfig.SIGNIFICANT_IMPACT_THRESHOLD:
                impact_level = "significantly"
            elif abs_change > AppConfig.MODERATE_IMPACT_THRESHOLD:
                impact_level = "moderately"
            else:
                impact_level = "minimally"
            
            direction = "benefits from" if income_change > 0 else "is burdened by"
            
            # Format values separately to avoid f-string corruption
            income_str = f"${income_change:,.0f}"
            pct_str = f"({income_pct_change:+.1f}%)"
            weight_str = f"{math.ceil(household_weight):,}"
            
            summary = (
                f"**Quick Story Angle:** This {profile.state} household {impact_level} {direction} the HR1 bill, "
                f"with a net income change of {income_str} {pct_str}. "
                f"The household represents approximately {weight_str} similar American families."
            )
            
            return summary
            
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Error generating story summary: {str(e)}")
            return "**Quick Story Angle:** Error generating summary. Please try a different household."


class HouseholdDashboard:
    """Main dashboard application orchestrator."""
    
    def __init__(self):
        """Initialize dashboard with configuration and data loading."""
        self._configure_page()
        self.data_manager = DataManager()
        self.filter_manager = FilterManager(FilterConfig.default())
        self.df = self.data_manager.load_data()
        logger.info("Dashboard initialized successfully")
    
    def _configure_page(self) -> None:
        """Configure Streamlit page settings."""
        st.set_page_config(
            page_title="HR1 Tax Impact Dashboard",
            layout="wide"
        )
    
    def run(self) -> None:
        """
        Run the main dashboard application.
        
        Orchestrates the entire dashboard flow: header, filters, household selection,
        analysis, and rendering.
        """
        try:
            self._render_header()
            
            # Apply filters and select household
            df_filtered = self.filter_manager.render_and_apply_filters(self.df)
            household_id = HouseholdSelector.select_household(df_filtered)
            household_data = self._get_household_data(df_filtered, household_id)
            profile = HouseholdProfile.from_series(household_data)
            
            # Set up analysis
            analysis_type = self._render_analysis_type_selector()
            analysis_engine = TaxAnalysisEngine(analysis_type)
            
            # Render main content
            renderer = VisualizationRenderer(analysis_engine)
            renderer.render_main_content(profile, household_data)
            
            # Generate and display story summary
            impacts = analysis_engine.get_reform_impacts(household_data)
            story_summary = StoryGenerator.generate_story_summary(profile, household_data, impacts)
            self._render_story_summary(story_summary)

            # Add analysis info card
            renderer.render_analysis_info_card()
            
        except Exception as e:
            logger.error(f"Error running dashboard: {str(e)}")
            st.error(f"An error occurred: {str(e)}")
    
    def _render_header(self) -> None:
        """Render dashboard header and title."""
        st.title("HR1 Tax Bill - Household Impact Dashboard")
        st.markdown("*Explore how the HR1 tax bill affects individual American households compared to current policy*")
        st.sidebar.header("Select Household")
    
    def _render_analysis_type_selector(self) -> AnalysisType:
        """
        Render analysis type selector in sidebar.
        
        Returns:
            AnalysisType: Selected analysis type
        """
        st.sidebar.markdown("---")
        st.sidebar.subheader("Analysis Type")
        
        analysis_type = st.sidebar.radio(
            "Select what to analyze:",
            [AnalysisType.FEDERAL_TAXES.value, AnalysisType.STATE_TAXES.value, AnalysisType.NET_INCOME.value],
            index=0
        )
        
        # Map string values back to enum
        type_mapping = {
            AnalysisType.FEDERAL_TAXES.value: AnalysisType.FEDERAL_TAXES,
            AnalysisType.STATE_TAXES.value: AnalysisType.STATE_TAXES,
            AnalysisType.NET_INCOME.value: AnalysisType.NET_INCOME
        }
        
        selected_type = type_mapping[analysis_type]
        st.session_state.analysis_type = selected_type
        return selected_type
    
    def _get_household_data(self, df_filtered: pd.DataFrame, household_id: int) -> pd.Series:
        """
        Get household data series for the selected household ID.
        
        Args:
            df_filtered: Filtered dataframe
            household_id: Selected household ID
            
        Returns:
            pd.Series: Household data series
            
        Raises:
            IndexError: If household ID not found
        """
        try:
            return df_filtered[df_filtered['Household ID'] == household_id].iloc[0]
        except IndexError:
            st.error(f"Household ID {household_id} not found. Please try different filters.")
            st.stop()
    
    def _render_story_summary(self, story_summary: str) -> None:
        """Render story summary section."""
        st.subheader("📝 Story Summary")
        st.info(story_summary)


def main() -> None:
    """
    Application entry point.
    
    Initializes and runs the household dashboard with comprehensive error handling.
    """
    try:
        dashboard = HouseholdDashboard()
        dashboard.run()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        st.error("A fatal error occurred. Please refresh the page and try again.")


if __name__ == "__main__":
    main()
