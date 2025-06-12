# The logging is probably unnecessary, but I'll leave it just in case.
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnalysisType(Enum):
    """Analysis focus types for the dashboard"""
    FEDERAL_TAXES = "Federal Taxes"
    NET_INCOME = "Net Income"
    STATE_TAXES = "State Taxes"  # For future expansion


class Constants:
    """Application constants and configuration"""
    CSV_FILENAME = "household_tax_income_changes.csv"
    INCOME_CHANGE_THRESHOLD = 0.01
    SIGNIFICANT_IMPACT_THRESHOLD = 1000
    MODERATE_IMPACT_THRESHOLD = 100
    MAX_DEPENDENTS = 11
    CHART_HEIGHT = 500

    REFORM_COLS = [
        ("Tax Rate Reform", "Tax Rate Reform"),
        ("Standard Deduction Reform", "Standard Deduction Reform"),
        ("Exemption Reform", "Exemption Reform"),
        ("Child Tax Credit Reform", "CTC Reform"),
        ("QBID Reform", "QBID Reform"),
        ("AMT Reform", "AMT Reform"),
        ("SALT Reform", "SALT Reform"),
        ("Tip Income Exemption", "Tip Income Exempt"),
        ("Overtime Income Exemption", "Overtime Income Exempt"),
        ("Auto Loan Interest Deduction", "Auto Loan Interest ALD"),
        ("Miscellaneous Reform", "Miscellaneous Reform"),
        ("Other Itemized Deductions Reform", "Other Itemized Deductions Reform"),
        ("Pease Reform", "Pease Reform")
    ]


@dataclass
class FilterConfig:
    """Configuration for data filters"""
    weight_options: Dict[str, int]
    income_ranges: Dict[str, Tuple[float, float]]
    age_ranges: Dict[str, Tuple[int, int]]
    dependent_options: List[str]
    marital_options: List[str]

    @classmethod
    def default(cls) -> 'FilterConfig':
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
            marital_options=["All", "Married", "Single"]
        )


@dataclass
class ReformImpact:
    """Represents the impact of a single tax reform"""
    name: str
    total_change: float
    
    @property
    def is_significant(self) -> bool:
        return abs(self.total_change) > Constants.INCOME_CHANGE_THRESHOLD


@dataclass
class HouseholdProfile:
    """Household demographic and financial profile"""
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
    """Handles data loading and validation"""
    
    @staticmethod
    @st.cache_data
    def load_data() -> pd.DataFrame:
        """Load and validate household data"""
        try:
            df = pd.read_csv(Constants.CSV_FILENAME)
            DataManager._validate_data(df)
            logger.info(f"Successfully loaded {len(df)} records")
            return df
        except FileNotFoundError:
            st.error(f"Data file {Constants.CSV_FILENAME} not found")
            st.stop()
        except Exception as e:
            st.error(f"Error loading data: {str(e)}")
            st.stop()
    
    @staticmethod
    def _validate_data(df: pd.DataFrame) -> None:
        """Validate required columns exist"""
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
    """Manages data filtering operations"""
    
    def __init__(self, config: FilterConfig):
        self.config = config
    
    def render_and_apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        """Render filter UI and return filtered dataframe"""
        with st.sidebar.expander("🔍 Filters"):
            df_filtered = df.copy()
            
            # Apply each filter sequentially
            df_filtered = self._apply_weight_filter(df_filtered)
            df_filtered = self._apply_income_filter(df_filtered)
            df_filtered = self._apply_state_filter(df_filtered, df)
            df_filtered = self._apply_marital_filter(df_filtered)
            df_filtered = self._apply_dependents_filter(df_filtered)
            df_filtered = self._apply_age_filter(df_filtered)
            
            self._display_filter_results(df_filtered, df)
            
        return df_filtered
    
    def _apply_weight_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        selected = st.selectbox("Minimum Household Weight:", list(self.config.weight_options.keys()))
        min_weight = self.config.weight_options[selected]
        return df[df['Household Weight'] >= min_weight] if min_weight > 0 else df
    
    def _apply_income_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        selected = st.selectbox("Net Income:", list(self.config.income_ranges.keys()))
        min_income, max_income = self.config.income_ranges[selected]
        if min_income > 0 or max_income < float('inf'):
            return df[(df['Baseline Net Income'] >= min_income) & 
                     (df['Baseline Net Income'] <= max_income)]
        return df
    
    def _apply_state_filter(self, df_filtered: pd.DataFrame, df_original: pd.DataFrame) -> pd.DataFrame:
        states = ["All States"] + sorted(df_original['State'].unique().tolist())
        selected = st.selectbox("State:", states)
        return df_filtered[df_filtered['State'] == selected] if selected != "All States" else df_filtered
    
    def _apply_marital_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        selected = st.selectbox("Marital Status:", self.config.marital_options)
        if selected != "All":
            is_married = selected == "Married"
            return df[df['Is Married'] == is_married]
        return df
    
    def _apply_dependents_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        selected = st.selectbox("Number of Dependents:", self.config.dependent_options)
        if selected != "All":
            if selected == "3+":
                return df[df['Number of Dependents'] >= 3]
            else:
                return df[df['Number of Dependents'] == int(selected)]
        return df
    
    def _apply_age_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        selected = st.selectbox("Head of Household Age:", list(self.config.age_ranges.keys()))
        min_age, max_age = self.config.age_ranges[selected]
        if selected != "All Ages":
            return df[(df['Age of Head'] >= min_age) & (df['Age of Head'] < max_age)]
        return df
    
    def _display_filter_results(self, df_filtered: pd.DataFrame, df_original: pd.DataFrame) -> None:
        st.caption(f"📊 Showing {len(df_filtered):,} of {len(df_original):,} households")
        if len(df_filtered) == 0:
            st.error("No households match your filters!")
            st.stop()


class HouseholdSelector:
    """Handles household selection methods"""
    
    @staticmethod
    def select_household(df_filtered: pd.DataFrame) -> int:
        """Select household based on user choice"""
        selection_method = st.sidebar.radio(
            "Selection Method:",
            ["By Household ID", "Find Interesting Cases", "Random Shuffle"]
        )
        
        if selection_method == "By Household ID":
            return HouseholdSelector._select_by_id(df_filtered)
        elif selection_method == "Random Shuffle":
            return HouseholdSelector._select_random(df_filtered)
        else:
            return HouseholdSelector._select_interesting_case(df_filtered)
    
    @staticmethod
    def _select_by_id(df_filtered: pd.DataFrame) -> int:
        return int(st.sidebar.selectbox("Choose Household ID:", df_filtered['Household ID'].unique()))
    
    @staticmethod
    def _select_random(df_filtered: pd.DataFrame) -> int:
        if st.sidebar.button("🎲 Get Random Household"):
            st.session_state.random_household = df_filtered['Household ID'].sample(1).iloc[0]
        
        if 'random_household' not in st.session_state:
            st.session_state.random_household = df_filtered['Household ID'].sample(1).iloc[0]
        
        household_id = st.session_state.random_household
        st.sidebar.info(f"Random Household ID: {household_id}")
        return int(household_id)
    
    @staticmethod
    def _select_interesting_case(df_filtered: pd.DataFrame) -> int:
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
            st.error("Error retrieving households. Please try different filters.")
            st.stop()
    
    @staticmethod
    def _create_ranked_options(top_households: pd.DataFrame, case_type: str) -> Tuple[List[str], List[int]]:
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


class AnalysisEngine(ABC):
    """Abstract base class for different analysis types"""
    
    @abstractmethod
    def get_reform_impacts(self, household_data: pd.Series) -> List[ReformImpact]:
        """Calculate reform impacts for the specific analysis type"""
        pass
    
    @abstractmethod
    def get_chart_title(self) -> str:
        """Get the waterfall chart title"""
        pass
    
    @abstractmethod
    def get_baseline_value(self, household_data: pd.Series) -> float:
        """Get baseline value for waterfall chart"""
        pass
    
    @abstractmethod
    def get_total_change(self, household_data: pd.Series) -> float:
        """Get total change for verification"""
        pass


class FederalTaxAnalysis(AnalysisEngine):
    """Analysis engine for Federal Tax impacts"""
    
    def get_reform_impacts(self, household_data: pd.Series) -> List[ReformImpact]:
        reform_configs = Constants.REFORM_COLS
        
        impacts = []
        for display_name, col_name in reform_configs:
            try:
                tax_change = household_data[f'Change in Federal tax liability after {col_name}']
                
                impact = ReformImpact(
                    name=display_name,
                    total_change=tax_change,
                )
                
                if impact.is_significant:
                    impacts.append(impact)
            except KeyError:
                continue
        
        return impacts
    
    def get_chart_title(self) -> str:
        return "Federal Tax Liability"
    
    def get_baseline_value(self, household_data: pd.Series) -> float:
        return household_data['Baseline Federal Tax Liability']
    
    def get_total_change(self, household_data: pd.Series) -> float:
        return household_data['Total Change in Federal Tax Liability']


class NetIncomeAnalysis(AnalysisEngine):
    """Analysis engine for Net Income impacts"""
    
    def get_reform_impacts(self, household_data: pd.Series) -> List[ReformImpact]:
        reform_configs = Constants.REFORM_COLS
        
        impacts = []
        for display_name, col_name in reform_configs:
            try:
                income_change = household_data[f'Change in Net income after {col_name}']
                
                impact = ReformImpact(
                    name=display_name,
                    total_change=income_change
                )
                
                if impact.is_significant:
                    impacts.append(impact)
            except KeyError:
                continue
        
        return impacts
    
    def get_chart_title(self) -> str:
        return "Net Income"
    
    def get_baseline_value(self, household_data: pd.Series) -> float:
        return household_data['Baseline Net Income']
    
    def get_total_change(self, household_data: pd.Series) -> float:
        return household_data['Total Change in Net Income']


class VisualizationRenderer:
    """Handles all UI rendering operations"""
    
    def __init__(self, analysis_engine: AnalysisEngine):
        self.analysis_engine = analysis_engine
    
    def render_sidebar_household_info(self, profile: HouseholdProfile, household_data: pd.Series) -> None:
        """Render household information in sidebar"""
        st.sidebar.subheader("Baseline Household Attributes")
        
        # Basic demographics
        st.sidebar.markdown(f"""
        **State:** {profile.state}  
        **Head of Household Age:** {profile.age_of_head:.0f} years  
        **Number of Dependents:** {profile.number_of_dependents:.0f}""")
        
        # Children's ages
        self._render_dependent_ages(household_data, profile.number_of_dependents)
        
        # Marital status
        self._render_marital_status(profile.is_married, profile.age_of_spouse)
        
        # Income sources
        self._render_income_sources(household_data)
        
        # Raw data expander
        self._render_raw_data_expander(household_data)
    
    def _render_dependent_ages(self, household_data: pd.Series, num_dependents: int) -> None:
        if num_dependents > 0:
            dependent_ages = []
            for i in range(1, Constants.MAX_DEPENDENTS + 1):
                age_col = f'Age of Dependent {i}'
                if age_col in household_data.index:
                    age = household_data[age_col]
                    if pd.notna(age) and age > 0:
                        dependent_ages.append(f"{age:.0f}")
            
            if dependent_ages:
                st.sidebar.markdown(f"**Children's Ages:** {', '.join(dependent_ages)} years")
    
    def _render_marital_status(self, is_married: bool, age_of_spouse: Optional[float]) -> None:
        if is_married and age_of_spouse:
            st.sidebar.markdown(f"""**Marital Status:** Married  
        **Spouse Age:** {age_of_spouse:.0f} years""")
        else:
            st.sidebar.markdown("**Marital Status:** Single")
    
    def _render_income_sources(self, household_data: pd.Series) -> None:
        st.sidebar.markdown("**Income Sources:**")
        income_sources = [
            ("Employment Income", household_data.get('Employment Income', 0)),
            ("Self-Employment Income", household_data.get('Self-Employment Income', 0)),
            ("Tip Income", household_data.get('Tip Income', 0)),
            ("Overtime Income", household_data.get('Overtime Income', 0)),
            ("Capital Gains", household_data.get('Capital Gains', 0))
        ]
        
        for source_name, amount in income_sources:
            if amount > 0:
                st.sidebar.markdown(f"• {source_name}: ${amount:,.2f}")
    
    def _render_raw_data_expander(self, household_data: pd.Series) -> None:
        with st.sidebar.expander("Full Dataframe Row"):
            st.dataframe(household_data.to_frame().T, use_container_width=True)
    
    def render_main_content(self, profile: HouseholdProfile, household_data: pd.Series) -> None:
        """Render main dashboard content"""
        col1, col2 = st.columns(2)
        
        with col1:
            self._render_baseline_info(profile, household_data)
        
        with col2:
            self._render_impact_summary(household_data)
        
        # Get impacts and render analysis
        impacts = self.analysis_engine.get_reform_impacts(household_data)
        self._render_reform_breakdown(impacts)
        
        if impacts:
            self._render_waterfall_chart(impacts, household_data)
        else:
            st.info("This household is not significantly affected by any specific reform components.")
    
    def _render_baseline_info(self, profile: HouseholdProfile, household_data: pd.Series) -> None:
        st.subheader("Baseline Federal Tax and Net Income")
        
        with st.container():
            st.metric("Federal Tax Liability", f"${profile.baseline_federal_tax:,.2f}")
            st.metric("Net Income", f"${profile.baseline_net_income:,.2f}")
            
            # Additional taxes
            state_tax = household_data.get('State Income Tax', 0)
            property_tax = household_data.get('Property Taxes', 0)
            
            if state_tax > 0:
                st.markdown(f"**State Income Tax:** ${state_tax:,.2f}")
            if property_tax > 0:
                st.markdown(f"**Property Taxes:** ${property_tax:,.2f}")
    
    def _render_impact_summary(self, household_data: pd.Series) -> None:
        st.subheader("🔄 HR1 Bill Impact Summary")
        
        with st.container():
            tax_change = household_data['Total Change in Federal Tax Liability']
            income_change = household_data['Total Change in Net Income']
            tax_pct_change = household_data['Percentage Change in Federal Tax Liability']
            income_pct_change = household_data['Percentage Change in Net Income']
            
            # Color coding
            tax_color = "red" if tax_change > 0 else "green"
            income_color = "green" if income_change > 0 else "red"
            
            st.markdown(f"""
            <div style="padding: 10px; border-radius: 5px; background-color: #f0f2f6;">
            <h4>Overall Impact</h4>
            <p style="color: {tax_color}; font-size: 18px; font-weight: bold;">
            Tax Change: ${tax_change:,.2f} ({tax_pct_change:+.1f}%)
            </p>
            <p style="color: {income_color}; font-size: 18px; font-weight: bold;">
            Net Income Change: ${income_change:,.2f} ({income_pct_change:+.1f}%)
            </p>
            </div>
            """, unsafe_allow_html=True)
        
        # Statistical weight
        weight = household_data['Household Weight']
        st.subheader("📈 Statistical Weight")
        with st.container():
            st.metric("Population Weight", f"{math.ceil(weight):,}")
            st.caption("This household represents approximately this many similar households in the U.S.")
    
    def _render_reform_breakdown(self, impacts: List[ReformImpact]) -> None:
        st.subheader("🔍 Detailed Reform Component Analysis")
        
        if impacts:
            cols = st.columns(min(3, len(impacts)))
            for i, impact in enumerate(impacts):
                with cols[i % 3]:
                    # For tax analysis, show tax changes; for income analysis, show income changes
                    if isinstance(self.analysis_engine, FederalTaxAnalysis):
                        value = impact.total_change
                        label = "Tax Change"
                        color = "green" if value < 0 else "red"  # Negative tax change is good
                    else:
                        value = impact.total_change
                        label = "Income Change"
                        color = "green" if value > 0 else "red"  # Positive income change is good
                    
                    st.markdown(f"""
                    <div style="padding: 8px; border-radius: 5px; background-color: #f9f9f9; margin: 5px 0;">
                    <h5>{impact.name}</h5>
                    <p style="color: {color}; font-weight: bold;">
                    {label}: ${value:,.2f}
                    </p>
                    </div>
                    """, unsafe_allow_html=True)
    
    def _render_waterfall_chart(self, impacts: List[ReformImpact], household_data: pd.Series) -> None:
        chart_title = self.analysis_engine.get_chart_title()
        st.subheader(f"📊 {chart_title} Impact Waterfall Chart")
        
        try:
            baseline = self.analysis_engine.get_baseline_value(household_data)
            total_change = self.analysis_engine.get_total_change(household_data)
            
            # Prepare waterfall data
            waterfall_data = [(f"Baseline {chart_title}", baseline, baseline)]
            running_total = baseline
            
            for impact in impacts:
                change_value = impact.total_change
                running_total += change_value
                waterfall_data.append((impact.name, change_value, running_total))
            
            final_value = baseline + total_change
            waterfall_data.append((f"Final {chart_title}", final_value, final_value))
            
            # Create chart
            fig = go.Figure()
            fig.add_trace(go.Waterfall(
                name=f"{chart_title} Impact",
                orientation="v",
                measure=["absolute"] + ["relative"] * len(impacts) + ["total"],
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
                title=f"{chart_title} Changes: ${baseline:,.0f} → ${final_value:,.0f}",
                xaxis_title="Reform Components",
                yaxis_title=f"{chart_title} ($)",
                showlegend=False,
                height=Constants.CHART_HEIGHT,
                xaxis={'tickangle': -45}
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
        except Exception as e:
            logger.error(f"Error creating waterfall chart: {str(e)}")
            st.error("Error creating waterfall chart. Please try a different household.")

    def render_analysis_info_card(self) -> None:
        """Render information card about current analysis scope"""
        st.markdown("---")  # Add separator line
        
        # Get list of reforms being analyzed
        reform_names = [display_name for display_name, _ in Constants.REFORM_COLS]
        
        # Format the list nicely
        if len(reform_names) > 1:
            reforms_text = ", ".join(reform_names[:-1]) + f", and {reform_names[-1]}"
        else:
            reforms_text = reform_names[0]
        
        # Determine analysis focus based on engine type
        if isinstance(self.analysis_engine, FederalTaxAnalysis):
            analysis_focus = "Federal Taxes"
        elif isinstance(self.analysis_engine, NetIncomeAnalysis):
            analysis_focus = "Net Income overall"
        else:
            analysis_focus = "the selected tax type"
        
        # Create the info card
        st.info(f"""
        📋 **Analysis Scope:** We are currently analyzing the effects of {reforms_text} on {analysis_focus}.
        """)


class StoryGenerator:
    """Generates journalist-friendly story summaries"""
    
    @staticmethod
    def generate_story_summary(profile: HouseholdProfile, household_data: pd.Series, 
                             impacts: List[ReformImpact]) -> str:
        income_change = household_data['Total Change in Net Income']
        income_pct_change = household_data['Percentage Change in Net Income']
        
        # Determine impact level
        abs_change = abs(income_change)
        if abs_change > Constants.SIGNIFICANT_IMPACT_THRESHOLD:
            impact_level = "significantly"
        elif abs_change > Constants.MODERATE_IMPACT_THRESHOLD:
            impact_level = "moderately"
        else:
            impact_level = "minimally"
        
        direction = "benefits from" if income_change > 0 else "is burdened by"
        
        # Get biggest impact
        if impacts:
            biggest_impact = max(impacts, key=lambda x: abs(x.total_change))
            biggest_reform_text = (f"The biggest change comes from the {biggest_impact.name} "
                                 f"(${biggest_impact.total_change:+,.2f}).")
        else:
            biggest_reform_text = "No single reform has a major impact."
        
        return (f"**Quick Story Angle:** This {profile.state} household "
                f"{impact_level} {direction} the HR1 bill, with a net income change of $"
                f"{income_change:,.2f} ({income_pct_change:+.1f}%). {biggest_reform_text} "
                f"The household represents approximately {math.ceil(profile.household_weight):,} "
                f"similar American families.")


class HouseholdDashboard:
    """Main dashboard application orchestrator"""
    
    def __init__(self):
        self._configure_page()
        self.data_manager = DataManager()
        self.filter_manager = FilterManager(FilterConfig.default())
        self.df = self.data_manager.load_data()
        logger.info("Dashboard initialized successfully")
    
    def _configure_page(self) -> None:
        st.set_page_config(
            page_title="HR1 Tax Impact Dashboard",
            page_icon="🏠",
            layout="wide"
        )
    
    def run(self) -> None:
        """Run the main dashboard application"""
        try:
            self._render_header()
            
            # Apply filters
            df_filtered = self.filter_manager.render_and_apply_filters(self.df)
            
            # Select household
            household_id = HouseholdSelector.select_household(df_filtered)
            household_data = self._get_household_data(df_filtered, household_id)
            profile = HouseholdProfile.from_series(household_data)
            
            # Render sidebar info
            self._render_analysis_type_selector()
            analysis_type = st.session_state.get('analysis_type', AnalysisType.FEDERAL_TAXES)
            
            # Create analysis engine based on selection
            analysis_engine = self._create_analysis_engine(analysis_type)
            
            # Render UI
            renderer = VisualizationRenderer(analysis_engine)
            renderer.render_sidebar_household_info(profile, household_data)
            renderer.render_main_content(profile, household_data)
            
            # Generate story summary
            impacts = analysis_engine.get_reform_impacts(household_data)
            story_summary = StoryGenerator.generate_story_summary(profile, household_data, impacts)
            self._render_story_summary(story_summary)

            # Add analysis info card at the bottom
            renderer.render_analysis_info_card()
            
        except Exception as e:
            logger.error(f"Error running dashboard: {str(e)}")
            st.error(f"An error occurred: {str(e)}")
    
    def _render_header(self) -> None:
        st.title("🏠 HR1 Tax Bill - Household Impact Dashboard")
        st.markdown("*Explore how the HR1 tax bill affects individual American households compared to current policy*")
        st.sidebar.header("Select Household")
    
    def _render_analysis_type_selector(self) -> None:
        st.sidebar.markdown("---")
        st.sidebar.subheader("Analysis Type")
        
        analysis_type = st.sidebar.radio(
            "Select what to analyze:",
            [AnalysisType.FEDERAL_TAXES.value, AnalysisType.NET_INCOME.value],
            index=0
        )
        
        # Store in session state for consistency
        if analysis_type == AnalysisType.FEDERAL_TAXES.value:
            st.session_state.analysis_type = AnalysisType.FEDERAL_TAXES
        else:
            st.session_state.analysis_type = AnalysisType.NET_INCOME
    
    def _create_analysis_engine(self, analysis_type: AnalysisType) -> AnalysisEngine:
        """Factory method to create appropriate analysis engine"""
        if analysis_type == AnalysisType.FEDERAL_TAXES:
            return FederalTaxAnalysis()
        elif analysis_type == AnalysisType.NET_INCOME:
            return NetIncomeAnalysis()
        else:
            raise ValueError(f"Unsupported analysis type: {analysis_type}")
    
    def _get_household_data(self, df_filtered: pd.DataFrame, household_id: int) -> pd.Series:
        try:
            return df_filtered[df_filtered['Household ID'] == household_id].iloc[0]
        except IndexError:
            st.error(f"Household ID {household_id} not found. Please try different filters.")
            st.stop()
    
    def _render_story_summary(self, story_summary: str) -> None:
        st.subheader("📝 Story Summary")
        st.info(story_summary)
    


def main() -> None:
    """Application entry point"""
    try:
        dashboard = HouseholdDashboard()
        dashboard.run()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        st.error("A fatal error occurred. Please refresh the page and try again.")


if __name__ == "__main__":
    main()
