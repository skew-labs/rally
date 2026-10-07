// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import "./RallyCommunity.sol";

interface INadRevenueRouter {
    struct BuyParams {uint256 amountIn;uint256 amountOutMin;address token;address to;uint256 deadline;}
    function buy(BuyParams calldata params) external returns(uint256);
}

/// External nad.fun token revenue. Never grants a keeper arbitrary call authority.
/// Creator-configured token floor is a limit price, not an inferred market oracle.
contract RallyNadRevenueVault is ReentrancyGuard {
    using SafeERC20 for IERC20;
    uint256 private constant Q112=2**112;
    address public constant BURN_ADDRESS=0x000000000000000000000000000000000000dEaD;
    address public immutable creator;
    IERC20 public immutable quoteToken;
    IERC20 public immutable wrappedToken;
    IERC20 public immutable communityToken;
    IV2Router public immutable router;
    INadRevenueRouter public immutable nadRouter;
    IV2Pair public immutable pair;
    bool public immutable quoteIsToken0;
    uint16 public buybackBps;
    uint16 public burnBps;
    uint16 public slippageBps;
    uint64 public policyNonce=1;
    uint256 public minBatchRaw=10_000;
    uint256 public maxBatchRaw;
    uint256 public minTokensPerUSDC;
    uint256 public pendingBuyback;
    uint256 public grossRevenue;
    uint256 public creatorPaid;
    uint256 public quoteSpent;
    uint256 public tokensBought;
    uint256 public tokensBurned;
    bool public paused;
    mapping(bytes32=>bool) public invoices;
    uint256 public observationCumulative;
    uint32 public observationTime;
    uint256 public averageQ112;
    uint32 public averageTime;
    event RevenuePaid(bytes32 indexed invoiceId,bytes32 indexed feedId,address indexed buyer,uint256 amount,uint256 creatorAmount,uint256 buybackAmount,uint64 policy);
    event BuybackExecuted(uint256 quoteAmount,uint256 tokenAmount,uint256 burned,uint256 treasuryTokens);
    event PolicyUpdated(uint64 indexed nonce,uint16 buybackBps,uint16 burnBps,uint16 slippageBps,uint256 minTokensPerUSDC,uint256 maxBatchRaw);
    event Paused(bool paused);
    constructor(address creator_,address usdc,address wmon,address token_,address dex,address nad,uint16 bb,uint16 burn_,uint16 slip,uint256 floor_,uint256 batch_) {
        require(creator_!=address(0)&&usdc!=wmon&&token_!=usdc&&token_!=wmon,"ASSETS");
        require(token_.code.length>0&&nad.code.length>0,"CODE");
        creator=creator_;quoteToken=IERC20(usdc);wrappedToken=IERC20(wmon);communityToken=IERC20(token_);
        router=IV2Router(dex);nadRouter=INadRevenueRouter(nad);
        address p=IV2Factory(router.factory()).getPair(usdc,wmon);require(p!=address(0),"NO_QUOTE_POOL");
        pair=IV2Pair(p);bool first=pair.token0()==usdc;quoteIsToken0=first;
        require((first&&pair.token1()==wmon)||(!first&&pair.token0()==wmon&&pair.token1()==usdc),"PAIR_ASSETS");
        _policy(bb,burn_,slip,floor_,batch_);(observationCumulative,observationTime)=_cumulative();
    }
    modifier onlyCreator(){require(msg.sender==creator,"CREATOR_ONLY");_;}
    function _policy(uint16 bb,uint16 burn_,uint16 slip,uint256 floor_,uint256 batch_) private {
        require(bb<=10000&&burn_<=10000&&slip>0&&slip<=500,"BPS");
        require(floor_>0&&floor_<=type(uint128).max&&batch_>=minBatchRaw&&batch_<=1_000_000_000,"LIMITS");
        buybackBps=bb;burnBps=burn_;slippageBps=slip;minTokensPerUSDC=floor_;maxBatchRaw=batch_;
    }
    function setPolicy(uint16 bb,uint16 burn_,uint16 slip,uint256 floor_,uint256 batch_) external onlyCreator {
        _policy(bb,burn_,slip,floor_,batch_);policyNonce++;emit PolicyUpdated(policyNonce,bb,burn_,slip,floor_,batch_);
    }
    function setPaused(bool value) external onlyCreator {paused=value;emit Paused(value);}
    function pay(bytes32 invoiceId,bytes32 feedId,uint256 amount,uint64 expectedPolicy) external nonReentrant {
        require(invoiceId!=bytes32(0)&&feedId!=bytes32(0)&&amount>0,"INVOICE");
        require(!invoices[invoiceId],"REPLAY");require(expectedPolicy==policyNonce,"POLICY_CHANGED");invoices[invoiceId]=true;
        uint256 before_=quoteToken.balanceOf(address(this));quoteToken.safeTransferFrom(msg.sender,address(this),amount);
        require(quoteToken.balanceOf(address(this))-before_==amount,"EXACT_PAYMENT");
        uint256 reserved=amount*buybackBps/10000;uint256 payout=amount-reserved;
        pendingBuyback+=reserved;grossRevenue+=amount;creatorPaid+=payout;
        if(payout>0)quoteToken.safeTransfer(creator,payout);
        emit RevenuePaid(invoiceId,feedId,msg.sender,amount,payout,reserved,policyNonce);
        if(!paused&&pendingBuyback>=minBatchRaw){try this.autoExecute() {} catch {}}
    }
    function _cumulative() private view returns(uint256 cumulative,uint32 timestamp){
        (uint112 r0,uint112 r1,uint32 last)=pair.getReserves();require(r0>0&&r1>0,"NO_LIQUIDITY");timestamp=uint32(block.timestamp);
        cumulative=quoteIsToken0?pair.price0CumulativeLast():pair.price1CumulativeLast();uint32 elapsed;unchecked{elapsed=timestamp-last;}
        if(elapsed>0){uint256 price=(uint256(quoteIsToken0?r1:r0)<<112)/(quoteIsToken0?r0:r1);unchecked{cumulative+=price*elapsed;}}
    }
    function checkpoint() public returns(bool){
        (uint256 cumulative,uint32 timestamp)=_cumulative();uint32 elapsed;unchecked{elapsed=timestamp-observationTime;}
        if(elapsed<600)return false;uint256 delta;unchecked{delta=cumulative-observationCumulative;}
        averageQ112=delta/elapsed;averageTime=timestamp;observationCumulative=cumulative;observationTime=timestamp;return true;
    }
    function buybackLimits() public view returns(uint256 amount,uint256 minWrapped,uint256 minTokens,bool ready){
        uint32 age;unchecked{age=uint32(block.timestamp)-averageTime;}
        if(paused||averageQ112==0||age>1200)return(0,0,0,false);
        (uint112 r0,uint112 r1,)=pair.getReserves();uint256 reserve=quoteIsToken0?r0:r1;
        amount=pendingBuyback;if(amount>maxBatchRaw)amount=maxBatchRaw;if(amount>reserve/200)amount=reserve/200;
        if(amount<minBatchRaw)return(0,0,0,false);
        minWrapped=amount*averageQ112/Q112*(10000-slippageBps)/10000;
        minTokens=amount*minTokensPerUSDC/1_000_000;ready=minWrapped>0&&minTokens>0;
    }
    function autoExecute() external {require(msg.sender==address(this),"SELF_ONLY");_execute(block.timestamp+60);}
    function executeBuyback(uint256 deadline) external nonReentrant {_execute(deadline);}
    function _execute(uint256 deadline) private {
        require(deadline>=block.timestamp&&deadline<=block.timestamp+300,"DEADLINE");checkpoint();
        (uint256 amount,uint256 minWrapped,uint256 minTokens,bool ready)=buybackLimits();require(ready,"BUYBACK_PENDING");
        pendingBuyback-=amount;uint256 beforeWrapped=wrappedToken.balanceOf(address(this));uint256 beforeTokens=communityToken.balanceOf(address(this));
        quoteToken.forceApprove(address(router),amount);
        address[] memory path=new address[](2);path[0]=address(quoteToken);path[1]=address(wrappedToken);
        router.swapExactTokensForTokens(amount,minWrapped,path,address(this),deadline);quoteToken.forceApprove(address(router),0);
        uint256 received=wrappedToken.balanceOf(address(this))-beforeWrapped;require(received>=minWrapped,"QUOTE_DELIVERY");
        wrappedToken.forceApprove(address(nadRouter),received);
        nadRouter.buy(INadRevenueRouter.BuyParams(received,minTokens,address(communityToken),address(this),deadline));
        wrappedToken.forceApprove(address(nadRouter),0);
        require(wrappedToken.balanceOf(address(this))==beforeWrapped,"UNSPENT_QUOTE");
        uint256 bought=communityToken.balanceOf(address(this))-beforeTokens;require(bought>=minTokens,"DELIVERY");
        uint256 burned=bought*burnBps/10000;uint256 treasury=bought-burned;
        // nad.fun ERC20 is not assumed to support ERC20Burnable. This irreversibly
        // sinks bought tokens; it does not assert that totalSupply was reduced.
        if(burned>0)communityToken.safeTransfer(BURN_ADDRESS,burned);
        if(treasury>0)communityToken.safeTransfer(creator,treasury);
        quoteSpent+=amount;tokensBought+=bought;tokensBurned+=burned;
        emit BuybackExecuted(amount,bought,burned,treasury);
    }
}
