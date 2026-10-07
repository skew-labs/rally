// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import "./RallyNadRevenue.sol";
import "./Mocks.sol";
contract MockNadAsset is ERC20 {
    constructor() ERC20("Nad fixture","NAD"){}
    function mint(address to,uint256 amount) external {_mint(to,amount);}
}
contract MockNadBuy {
    IERC20 public immutable quote;
    uint256 public rate=1000;
    bool public fail;
    bool public partialSpend;
    constructor(address q){quote=IERC20(q);}
    function setRate(uint256 r) external {rate=r;}
    function setFail(bool f) external {fail=f;}
    function setPartial(bool f) external {partialSpend=f;}
    function buy(INadRevenueRouter.BuyParams calldata p) external returns(uint256 out){
        require(!fail&&p.deadline>=block.timestamp,"NAD_FAIL");out=p.amountIn*rate;
        require(out>=p.amountOutMin,"PRICE_LIMIT");
        quote.transferFrom(msg.sender,address(this),partialSpend?p.amountIn/2:p.amountIn);
        MockNadAsset(p.token).mint(p.to,out);
    }
}
