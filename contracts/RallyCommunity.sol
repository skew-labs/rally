// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

interface IV2Factory { function getPair(address,address) external view returns(address); }
interface IV2Router {
    function factory() external view returns(address);
    function addLiquidity(address,address,uint256,uint256,uint256,uint256,address,uint256) external returns(uint256,uint256,uint256);
    function getAmountsOut(uint256,address[] calldata) external view returns(uint256[] memory);
    function swapExactTokensForTokens(uint256,uint256,address[] calldata,address,uint256) external returns(uint256[] memory);
}
interface IV2Pair {
    function token0() external view returns(address);
    function token1() external view returns(address);
    function getReserves() external view returns(uint112,uint112,uint32);
    function price0CumulativeLast() external view returns(uint256);
    function price1CumulativeLast() external view returns(uint256);
}

/// Fixed supply, no admin mint, transfer tax or transfer restrictions.
contract RallyCommunityToken is ERC20Burnable {
    uint256 public constant INITIAL_SUPPLY = 1_000_000_000 ether;
    constructor(string memory name_, string memory symbol_) ERC20(name_,symbol_) {
        require(bytes(name_).length>0 && bytes(name_).length<=64,"NAME");
        require(bytes(symbol_).length>0 && bytes(symbol_).length<=12,"SYMBOL");
        _mint(msg.sender,INITIAL_SUPPLY);
    }
}

/// Each creator has a separate revenue vault. Pending buybacks cannot be withdrawn.
contract RallyCommunityVault is ReentrancyGuard {
    using SafeERC20 for IERC20;
    uint256 private constant Q112 = 2**112;
    uint32 public constant ORACLE_WINDOW = 600;
    uint32 public constant ORACLE_MAX_AGE = 1200;
    address public immutable creator;
    address public immutable launchFactory;
    IERC20 public immutable quoteToken;
    RallyCommunityToken public immutable communityToken;
    IV2Router public immutable router;
    IV2Pair public pair;
    bool public quoteIsToken0;
    uint16 public buybackBps;
    uint16 public burnBps;
    uint16 public slippageBps;
    uint64 public policyNonce = 1;
    uint256 public minBatchRaw = 10_000;
    uint256 public maxBatchRaw = 100_000_000;
    bool public paused;
    uint256 public pendingBuyback;
    uint256 public grossRevenue;
    uint256 public creatorPaid;
    uint256 public quoteSpent;
    uint256 public tokensBought;
    uint256 public tokensBurned;
    mapping(bytes32=>bool) public invoices;
    uint256 public observationCumulative;
    uint32 public observationTime;
    uint256 public averageQ112;
    uint32 public averageTime;

    event RevenuePaid(bytes32 indexed invoiceId,bytes32 indexed feedId,address indexed buyer,uint256 amount,uint256 creatorAmount,uint256 buybackAmount,uint64 policy);
    event BuybackExecuted(uint256 quoteAmount,uint256 tokenAmount,uint256 burned,uint256 treasuryTokens);
    event PolicyUpdated(uint64 indexed nonce,uint16 buybackBps,uint16 burnBps,uint16 slippageBps,uint256 minBatchRaw,uint256 maxBatchRaw);
    event Paused(bool paused);

    constructor(address creator_,address quote_,address token_,address router_,uint16 buyback_,uint16 burn_,uint16 slippage_) {
        require(creator_!=address(0),"CREATOR");
        creator=creator_;launchFactory=msg.sender;quoteToken=IERC20(quote_);
        communityToken=RallyCommunityToken(token_);router=IV2Router(router_);
        _policy(buyback_,burn_,slippage_,minBatchRaw,maxBatchRaw);
    }
    modifier onlyCreator(){require(msg.sender==creator,"CREATOR_ONLY");_;}
    function initializePair(address pair_) external {
        require(msg.sender==launchFactory && address(pair)==address(0),"INITIALIZED");
        require(IV2Factory(router.factory()).getPair(address(quoteToken),address(communityToken))==pair_,"PAIR_FACTORY");
        pair=IV2Pair(pair_);quoteIsToken0=pair.token0()==address(quoteToken);
        require((quoteIsToken0 && pair.token1()==address(communityToken)) || (pair.token0()==address(communityToken) && pair.token1()==address(quoteToken)),"PAIR_ASSETS");
        (observationCumulative,observationTime)=_cumulative();
    }
    function _policy(uint16 bb,uint16 burn_,uint16 slip,uint256 min_,uint256 max_) private {
        require(bb<=10000 && burn_<=10000 && slip>0 && slip<=500,"BPS");
        require(min_>=10_000 && max_>=min_ && max_<=1_000_000_000_000,"BATCH");
        buybackBps=bb;burnBps=burn_;slippageBps=slip;minBatchRaw=min_;maxBatchRaw=max_;
    }
    function setPolicy(uint16 bb,uint16 burn_,uint16 slip,uint256 min_,uint256 max_) external onlyCreator {
        _policy(bb,burn_,slip,min_,max_);policyNonce++;
        emit PolicyUpdated(policyNonce,bb,burn_,slip,min_,max_);
    }
    function setPaused(bool value) external onlyCreator {paused=value;emit Paused(value);}
    function pay(bytes32 invoiceId,bytes32 feedId,uint256 amount,uint64 expectedPolicy) external nonReentrant {
        require(invoiceId!=bytes32(0) && feedId!=bytes32(0) && amount>0,"INVOICE");
        require(!invoices[invoiceId],"REPLAY");require(expectedPolicy==policyNonce,"POLICY_CHANGED");
        invoices[invoiceId]=true;
        uint256 before_=quoteToken.balanceOf(address(this));
        quoteToken.safeTransferFrom(msg.sender,address(this),amount);
        require(quoteToken.balanceOf(address(this))-before_==amount,"EXACT_PAYMENT");
        uint256 reserved=amount*buybackBps/10000;
        uint256 payout=amount-reserved;
        pendingBuyback+=reserved;grossRevenue+=amount;creatorPaid+=payout;
        if(payout>0)quoteToken.safeTransfer(creator,payout);
        emit RevenuePaid(invoiceId,feedId,msg.sender,amount,payout,reserved,policyNonce);
        // A missing quote cannot deny paid access. The reserve remains in this vault.
        if(!paused && pendingBuyback>=minBatchRaw){try this.autoExecute() {} catch {}}
    }
    function _cumulative() private view returns(uint256 cumulative,uint32 timestamp) {
        require(address(pair)!=address(0),"NO_PAIR");
        (uint112 r0,uint112 r1,uint32 last)=pair.getReserves();
        require(r0>0 && r1>0,"NO_LIQUIDITY");timestamp=uint32(block.timestamp);
        cumulative=quoteIsToken0?pair.price0CumulativeLast():pair.price1CumulativeLast();
        uint32 elapsed;unchecked{elapsed=timestamp-last;}
        if(elapsed>0){
            uint256 price=(uint256(quoteIsToken0?r1:r0)<<112)/(quoteIsToken0?r0:r1);
            unchecked{cumulative+=price*elapsed;}
        }
    }
    function checkpoint() public returns(bool) {
        (uint256 cumulative,uint32 timestamp)=_cumulative();
        uint32 elapsed;unchecked{elapsed=timestamp-observationTime;}
        if(elapsed<ORACLE_WINDOW)return false;
        uint256 delta;unchecked{delta=cumulative-observationCumulative;}
        averageQ112=delta/elapsed;averageTime=timestamp;
        observationCumulative=cumulative;observationTime=timestamp;
        return true;
    }
    function buybackQuote() public view returns(uint256 amount,uint256 minimum,uint256 quoted,bool ready) {
        if(paused || address(pair)==address(0) || averageQ112==0)return(0,0,0,false);
        uint32 age;unchecked{age=uint32(block.timestamp)-averageTime;}
        if(age>ORACLE_MAX_AGE)return(0,0,0,false);
        (uint112 r0,uint112 r1,)=pair.getReserves();
        uint256 reserve=quoteIsToken0?r0:r1;
        amount=pendingBuyback;
        if(amount>maxBatchRaw)amount=maxBatchRaw;
        if(amount>reserve/200)amount=reserve/200;
        if(amount<minBatchRaw)return(0,0,0,false);
        minimum=amount*averageQ112/Q112*(10000-slippageBps)/10000;
        if(minimum==0)return(0,0,0,false);
        address[] memory path=new address[](2);path[0]=address(quoteToken);path[1]=address(communityToken);
        uint256[] memory amounts=router.getAmountsOut(amount,path);
        require(amounts.length==2 && amounts[0]==amount,"QUOTE");
        quoted=amounts[1];ready=quoted>=minimum;
    }
    function autoExecute() external {require(msg.sender==address(this),"SELF_ONLY");_execute(block.timestamp+60);}
    function executeBuyback(uint256 deadline) external nonReentrant {_execute(deadline);}
    function _execute(uint256 deadline) private {
        require(deadline>=block.timestamp && deadline<=block.timestamp+300,"DEADLINE");
        checkpoint();
        (uint256 amount,uint256 minimum,,bool ready)=buybackQuote();require(ready,"BUYBACK_PENDING");
        uint256 balanceBefore=communityToken.balanceOf(address(this));
        pendingBuyback-=amount;
        quoteToken.forceApprove(address(router),amount);
        address[] memory path=new address[](2);path[0]=address(quoteToken);path[1]=address(communityToken);
        router.swapExactTokensForTokens(amount,minimum,path,address(this),deadline);
        quoteToken.forceApprove(address(router),0);
        uint256 bought=communityToken.balanceOf(address(this))-balanceBefore;
        require(bought>=minimum,"DELIVERY");
        uint256 burned=bought*burnBps/10000;
        uint256 treasury=bought-burned;
        if(burned>0)communityToken.burn(burned);
        if(treasury>0)IERC20(address(communityToken)).safeTransfer(creator,treasury);
        quoteSpent+=amount;tokensBought+=bought;tokensBurned+=burned;
        emit BuybackExecuted(amount,bought,burned,treasury);
    }
}

/// One community token per creator wallet. All initial supply enters its USDC pool.
contract RallyCommunityFactory is ReentrancyGuard {
    using SafeERC20 for IERC20;
    IERC20 public immutable quoteToken;
    IV2Router public immutable router;
    mapping(address=>address) public vaultOf;
    event CommunityLaunched(address indexed creator,address indexed token,address indexed vault,address pair,uint256 seedUSDC,uint16 buybackBps,uint16 burnBps,uint16 slippageBps);
    constructor(address quote_,address router_) {
        require(block.chainid==143,"MONAD_ONLY");
        require(quote_.code.length>0 && router_.code.length>0,"CONTRACTS");
        quoteToken=IERC20(quote_);router=IV2Router(router_);
    }
    function launch(string calldata name_,string calldata symbol_,uint256 seedUSDC,uint16 bb,uint16 burn_,uint16 slip) external nonReentrant returns(address token_,address vault_,address pair_) {
        require(vaultOf[msg.sender]==address(0),"ONE_COMMUNITY");require(seedUSDC>=1_000_000 && seedUSDC<=1_000_000_000_000,"SEED");
        RallyCommunityToken token=new RallyCommunityToken(name_,symbol_);
        RallyCommunityVault vault=new RallyCommunityVault(msg.sender,address(quoteToken),address(token),address(router),bb,burn_,slip);
        vaultOf[msg.sender]=address(vault);
        uint256 before_=quoteToken.balanceOf(address(this));quoteToken.safeTransferFrom(msg.sender,address(this),seedUSDC);
        require(quoteToken.balanceOf(address(this))-before_==seedUSDC,"EXACT_SEED");
        uint256 supply=token.totalSupply();IERC20(address(token)).forceApprove(address(router),supply);quoteToken.forceApprove(address(router),seedUSDC);
        (uint256 usedToken,uint256 usedUSDC,)=router.addLiquidity(address(token),address(quoteToken),supply,seedUSDC,supply,seedUSDC,msg.sender,block.timestamp);
        require(usedToken==supply && usedUSDC==seedUSDC,"EXACT_LIQUIDITY");
        IERC20(address(token)).forceApprove(address(router),0);quoteToken.forceApprove(address(router),0);
        pair_=IV2Factory(router.factory()).getPair(address(token),address(quoteToken));vault.initializePair(pair_);
        token_=address(token);vault_=address(vault);
        emit CommunityLaunched(msg.sender,token_,vault_,pair_,seedUSDC,bb,burn_,slip);
    }
}
