from collections import defaultdict, deque
from typing import Dict, List, Tuple, Optional
import time
from models import Trade, Order


class SlidingWindow:
    """滑动时间窗口实现"""
    
    def __init__(self, window_size_seconds: int):
        self.window_size_ns = window_size_seconds * 1_000_000_000  # 转换为纳秒
        self.data = deque()  # 存储 (timestamp, value) 元组
        
    def add(self, timestamp: int, value: float):
        """添加数据点"""
        self.data.append((timestamp, value))
        self._cleanup(timestamp)
        
    def get_sum(self, current_time: int) -> float:
        """获取窗口内数据总和"""
        self._cleanup(current_time)
        return sum(value for _, value in self.data)
        
    def get_count(self, current_time: int) -> int:
        """获取窗口内数据点数量"""
        self._cleanup(current_time)
        return len(self.data)
        
    def _cleanup(self, current_time: int):
        """清理过期数据"""
        cutoff_time = current_time - self.window_size_ns
        while self.data and self.data[0][0] < cutoff_time:
            self.data.popleft()


class MultiDimensionalStatistics:
    """多维统计引擎"""
    
    def __init__(self):
        # 按账户统计
        self.account_trade_volume = defaultdict(lambda: SlidingWindow(86400))  # 日内成交量
        self.account_trade_amount = defaultdict(lambda: SlidingWindow(86400))  # 日内成交金额
        self.account_order_count = defaultdict(lambda: SlidingWindow(1))       # 每秒报单数
        self.account_order_count_minute = defaultdict(lambda: SlidingWindow(60))  # 每分钟报单数
        
        # 按合约统计
        self.contract_trade_volume = defaultdict(lambda: SlidingWindow(86400))
        self.contract_trade_amount = defaultdict(lambda: SlidingWindow(86400))
        
        # 按产品统计
        self.product_trade_volume = defaultdict(lambda: SlidingWindow(86400))
        self.product_trade_amount = defaultdict(lambda: SlidingWindow(86400))
        
        # 合约到产品的映射
        self.contract_to_product = {}
        self._init_contract_product_mapping()
        
    def _init_contract_product_mapping(self):
        """初始化合约到产品的映射关系"""
        # 国债期货产品映射示例
        treasury_contracts = ["T2303", "T2306", "T2309", "T2312"]
        for contract in treasury_contracts:
            self.contract_to_product[contract] = "10年期国债期货"
            
        # 可以扩展其他产品
        # self.contract_to_product["IF2303"] = "沪深300股指期货"
        
    def add_contract_product_mapping(self, contract_id: str, product_name: str):
        """动态添加合约产品映射"""
        self.contract_to_product[contract_id] = product_name
        
    def update_trade_statistics(self, trade: Trade, order: Order):
        """更新成交统计"""
        timestamp = trade.timestamp
        volume = trade.volume
        amount = trade.price * trade.volume
        
        # 按账户统计
        self.account_trade_volume[order.account_id].add(timestamp, volume)
        self.account_trade_amount[order.account_id].add(timestamp, amount)
        
        # 按合约统计
        self.contract_trade_volume[order.contract_id].add(timestamp, volume)
        self.contract_trade_amount[order.contract_id].add(timestamp, amount)
        
        # 按产品统计
        product = self.contract_to_product.get(order.contract_id)
        if product:
            self.product_trade_volume[product].add(timestamp, volume)
            self.product_trade_amount[product].add(timestamp, amount)
            
    def update_order_statistics(self, order: Order):
        """更新报单统计"""
        timestamp = order.timestamp
        
        # 按账户统计报单频率
        self.account_order_count[order.account_id].add(timestamp, 1)
        self.account_order_count_minute[order.account_id].add(timestamp, 1)
        
    def get_account_trade_volume(self, account_id: str, current_time: int) -> float:
        """获取账户日内成交量"""
        return self.account_trade_volume[account_id].get_sum(current_time)
        
    def get_account_trade_amount(self, account_id: str, current_time: int) -> float:
        """获取账户日内成交金额"""
        return self.account_trade_amount[account_id].get_sum(current_time)
        
    def get_account_order_frequency_per_second(self, account_id: str, current_time: int) -> int:
        """获取账户每秒报单数"""
        return self.account_order_count[account_id].get_count(current_time)
        
    def get_account_order_frequency_per_minute(self, account_id: str, current_time: int) -> int:
        """获取账户每分钟报单数"""
        return self.account_order_count_minute[account_id].get_count(current_time)
        
    def get_contract_trade_volume(self, contract_id: str, current_time: int) -> float:
        """获取合约成交量"""
        return self.contract_trade_volume[contract_id].get_sum(current_time)
        
    def get_product_trade_volume(self, product_name: str, current_time: int) -> float:
        """获取产品成交量"""
        return self.product_trade_volume[product_name].get_sum(current_time)
        
    def get_statistics_summary(self, current_time: int) -> Dict:
        """获取统计摘要"""
        summary = {
            "accounts": {},
            "contracts": {},
            "products": {}
        }
        
        # 账户统计
        for account_id in self.account_trade_volume.keys():
            summary["accounts"][account_id] = {
                "trade_volume": self.get_account_trade_volume(account_id, current_time),
                "trade_amount": self.get_account_trade_amount(account_id, current_time),
                "order_freq_per_sec": self.get_account_order_frequency_per_second(account_id, current_time),
                "order_freq_per_min": self.get_account_order_frequency_per_minute(account_id, current_time)
            }
            
        # 合约统计
        for contract_id in self.contract_trade_volume.keys():
            summary["contracts"][contract_id] = {
                "trade_volume": self.get_contract_trade_volume(contract_id, current_time)
            }
            
        # 产品统计
        for product_name in self.product_trade_volume.keys():
            summary["products"][product_name] = {
                "trade_volume": self.get_product_trade_volume(product_name, current_time)
            }
            
        return summary